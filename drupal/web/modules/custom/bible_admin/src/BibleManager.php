<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\File\FileSystemInterface;
use Drupal\Core\Logger\LoggerChannelFactoryInterface;
use Drupal\Core\Session\AccountInterface;
use Drupal\Core\Session\AccountProxyInterface;
use Drupal\Core\Site\Settings;
use Psr\Log\LoggerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\Process\Exception\ProcessTimedOutException;
use Symfony\Component\Process\Process;

/**
 * Talks to the Python tool that manages the Bible search database, and keeps uploads safe.
 *
 * Drupal never touches the Bible database itself. Every change goes through
 * ml-service/scripts/manage_bibles.py, which prints JSON. The command is run without a shell,
 * with a fixed list of arguments, so nothing an administrator types can become a command.
 */
class BibleManager {

  /**
   * Largest upload of a text file (a Bible, or a commentary, devotional or book as text), in bytes: 1 GB, like
   * the songs and the documents (the owner's choice, 2026-11-13; PHP and nginx allow as much).
   */
  public const MAX_UPLOAD_BYTES = 1024 * 1024 * 1024;

  /**
   * Largest PDF, Word document or EPUB for a commentary, devotional, book or a song's words
   * (document_import.MAX_DOCUMENT_BYTES): 1 GB.
   */
  public const MAX_DOCUMENT_BYTES = 1024 * 1024 * 1024;

  /**
   * The kinds of upload file kept, by extension: text (.txt, .tsv), PDF and Word.
   */
  private const UPLOAD_EXTENSIONS = ['txt', 'tsv', 'pdf', 'docx', 'epub'];

  private const UPLOAD_FOLDER = 'bible-uploads';

  private const COMMAND_TIMEOUT_SECONDS = 180;

  /**
   * How long a PDF or Word document may take to read: a long scan is read by text recognition, a page or two a
   * second (nginx's fastcgi_read_timeout for the admin site allows as long).
   */
  private const DOCUMENT_TIMEOUT_SECONDS = 600;

  private const STALE_UPLOAD_SECONDS = 86400;

  private const TOKEN_PATTERN = '/^[0-9a-f]{32}$/';

  private LoggerInterface $logger;

  public function __construct(
    private readonly FileSystemInterface $fileSystem,
    LoggerChannelFactoryInterface $loggerFactory,
    private readonly AccountProxyInterface $currentUser,
  ) {
    $this->logger = $loggerFactory->get('bible_admin');
  }

  /**
   * The translations in the search database, including hidden ones.
   */
  public function listTranslations(): array {
    return $this->run(['list'])['translations'];
  }

  /**
   * The file formats the importer understands.
   */
  public function listFormats(): array {
    return $this->run(['formats'])['formats'];
  }

  /**
   * Reads an uploaded file and says what an import would do. Saves nothing.
   */
  public function preview(string $path, array $parameters): array {
    return $this->run(['preview', ...$this->fileArguments($path, $parameters)]);
  }

  /**
   * Imports an uploaded file. A new translation stays hidden until it is published.
   */
  public function import(string $path, array $parameters): array {
    $result = $this->run(['import', ...$this->fileArguments($path, $parameters)]);
    $this->logger->notice('@user imported @code (@count verses, @state).', [
      '@user' => $this->currentUser->getAccountName(),
      '@code' => $result['code'],
      '@count' => $result['verse_count'],
      '@state' => $result['is_published'] ? 'published' : 'hidden',
    ]);
    return $result;
  }

  /**
   * The site settings an administrator can change, and what each may be.
   *
   * @return array
   *   Keys: settings (the three verse-window numbers, site_title and copyright_text), limits (for
   *   each number, min and max) and text_limits (for each text, the fewest and most characters).
   */
  public function getSiteSettings(): array {
    return $this->run(['get'], 'manage_settings.py');
  }

  /**
   * Saves the settings that are given; any that are left out stay as they were.
   *
   * The public site uses them straight away. The email settings are not among them: they live in
   * Drupal (see MailSettings).
   *
   * @param array $values
   *   Any of: context_verses_before, context_verses_after, related_verses_limit (whole numbers),
   *   site_title and copyright_text (text).
   */
  public function saveSiteSettings(array $values): array {
    $options = [
      'context_verses_before' => '--context-verses-before=',
      'context_verses_after' => '--context-verses-after=',
      'related_verses_limit' => '--related-verses-limit=',
      'site_title' => '--site-title=',
      'copyright_text' => '--copyright-text=',
      // 'yes' or 'no'.
      'login_required' => '--login-required=',
      'check_posts' => '--check-posts=',
    ];
    $arguments = ['set'];
    $changed = [];
    foreach ($options as $key => $option) {
      if (array_key_exists($key, $values)) {
        $arguments[] = $option . $values[$key];
        $changed[] = $key;
      }
    }
    // The welcome paragraph: ['html' => ...] from the editor or ['text' => ...] from the plain box.
    if (isset($values['welcome_text']) && is_array($values['welcome_text'])) {
      $arguments[] = array_key_exists('html', $values['welcome_text'])
        ? '--welcome-html=' . $values['welcome_text']['html']
        : '--welcome-text=' . ($values['welcome_text']['text'] ?? '');
      $changed[] = 'welcome_text';
    }
    $result = $this->run($arguments, 'manage_settings.py');
    $this->logger->notice('@user changed the site settings: @changed.', [
      '@user' => $this->currentUser->getAccountName(),
      '@changed' => implode(', ', $changed),
    ]);
    return $result;
  }

  /**
   * Largest icon file, in bytes (site_icons.MAX_BYTES).
   */
  public const MAX_ICON_BYTES = 1024 * 1024;

  /**
   * The file types an icon may be (site_icons.TYPES).
   */
  public const ICON_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'ico', 'svg'];

  /**
   * The site's two icons: header (the emblem beside the name) and tab (the browser-tab icon). Each is NULL
   * while the site's own is used, else its media_type, size, version and data_uri (for a preview).
   */
  public function getSiteIcons(): array {
    return $this->run(['get'], 'manage_site_icons.py')['icons'];
  }

  /**
   * Replaces one icon with an uploaded file. The file waits in the private upload folder only while the tool
   * copies it, and is removed afterwards whatever happens.
   */
  public function saveSiteIcon(string $kind, UploadedFile $file): array {
    $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    try {
      $extension = strtolower($file->getClientOriginalExtension());
      $file->move($directory, 'icon.' . $extension);
      $icons = $this->run(
        ['upload', '--kind=' . $kind, '--file=' . $directory . '/icon.' . $extension, '--name=icon.' . $extension],
        'manage_site_icons.py',
      )['icons'];
    }
    finally {
      $this->fileSystem->deleteRecursive($directory);
    }
    $this->logger->notice('@user replaced the @kind icon.', ['@user' => $this->currentUser->getAccountName(), '@kind' => $kind]);
    return $icons;
  }

  /**
   * Goes back to the site's own icon of that kind.
   */
  public function removeSiteIcon(string $kind): array {
    $icons = $this->run(['remove', '--kind=' . $kind], 'manage_site_icons.py')['icons'];
    $this->logger->notice('@user removed the uploaded @kind icon.', ['@user' => $this->currentUser->getAccountName(), '@kind' => $kind]);
    return $icons;
  }

  /**
   * The commentaries or devotionals: those in the database, then the known ones not loaded.
   *
   * @param string $kind
   *   "commentary" or "devotional".
   *
   * @return array
   *   Each with id, name, detail (short name or author), source_name, is_published, count, loaded,
   *   refreshable and refresh (the state of a refresh started from here, or NULL).
   */
  public function listLibrary(string $kind): array {
    return $this->run(['list', '--kind=' . $kind], 'manage_library.py')['items'];
  }

  /**
   * Publishes, hides, deletes or refreshes (in the background) a commentary or devotional.
   */
  public function changeLibrary(string $kind, string $action, string $itemId): array {
    $result = $this->run([$action, '--kind=' . $kind, '--id=' . $itemId], 'manage_library.py');
    $this->logger->notice('@user chose @action for the @kind @id.', [
      '@user' => $this->currentUser->getAccountName(),
      '@action' => $action,
      '@kind' => $kind,
      '@id' => $itemId,
    ]);
    return $result;
  }

  /**
   * The details of one commentary, devotional or Other book, for its Edit page.
   *
   * @return array
   *   id, the editable details (name, short_name or author, translator, source_name, source_url, license_url
   *   or credit), is_published and refreshable.
   */
  public function getLibraryItem(string $kind, string $itemId): array {
    return $this->run(['get', '--kind=' . $kind, '--id=' . $itemId], 'manage_library.py')['item'];
  }

  /**
   * Changes the details of a commentary, devotional or Other book (not its text). They go on the tool's
   * input as JSON. The log names the item, not the details.
   */
  public function updateLibraryItem(string $kind, string $itemId, array $details): array {
    $input = json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
    $result = $this->run(['update', '--kind=' . $kind, '--id=' . $itemId], 'manage_library.py', $input);
    $this->logger->notice('@user changed the details of the @kind @id.', [
      '@user' => $this->currentUser->getAccountName(),
      '@kind' => $kind,
      '@id' => $itemId,
    ]);
    return $result['item'];
  }

  /**
   * What importing an uploaded commentary or devotional file would do. Saves nothing.
   */
  public function previewLibrary(string $path, array $parameters): array {
    return $this->run(['preview', ...$this->libraryArguments($path, $parameters)], 'manage_library.py');
  }

  /**
   * Imports one file of a multiple upload (the Bulk upload area on the Devotionals and Other books pages): the
   * file waits in the private upload folder, under its own extension, only while the tool reads it.
   */
  public function importLibraryUpload(UploadedFile $file, array $parameters): array {
    $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    try {
      $extension = strtolower($file->getClientOriginalExtension());
      $file->move($directory, 'upload.' . $extension);
      return $this->importLibrary($directory . '/upload.' . $extension, $parameters);
    }
    finally {
      $this->fileSystem->deleteRecursive($directory);
    }
  }

  /**
   * Imports an uploaded commentary or devotional file. A new one stays hidden until published.
   */
  public function importLibrary(string $path, array $parameters): array {
    $result = $this->run(['import', ...$this->libraryArguments($path, $parameters)], 'manage_library.py');
    $this->logger->notice('@user imported the @kind @id (@count entries).', [
      '@user' => $this->currentUser->getAccountName(),
      '@kind' => $parameters['kind'],
      '@id' => $result['id'],
      '@count' => $result['count'],
    ]);
    return $result;
  }

  /**
   * Arguments for a commentary or devotional preview or import, each joined to its option with "=".
   */
  private function libraryArguments(string $path, array $parameters): array {
    $arguments = [$path, '--kind=' . $parameters['kind']];
    // Keywords are sent only when typed, so uploading again with the box empty keeps the ones it has.
    foreach (['id', 'name', 'short_name', 'author', 'devotional_kind', 'source_name', 'source_url', 'license_url', 'translator', 'passage', 'keywords'] as $key) {
      if (($parameters[$key] ?? '') !== '') {
        $arguments[] = '--' . str_replace('_', '-', $key) . '=' . $parameters[$key];
      }
    }
    // A devotional's or book's own credit line is always sent, so an empty box brings back the usual line.
    if ($parameters['kind'] !== 'commentary') {
      $arguments[] = '--credit=' . ($parameters['credit'] ?? '');
      // A PDF or Word document kept whole as one chapter, not cut at its headings.
      if (!empty($parameters['whole'])) {
        $arguments[] = '--whole';
      }
    }
    // A PDF's pages kept as pictures and shown by the reader (any kind).
    if (!empty($parameters['original_pages'])) {
      $arguments[] = '--original-pages';
    }
    return $arguments;
  }

  /**
   * The keys and options of the outside services (Gemini, API.Bible, reCAPTCHA).
   *
   * @return array
   *   Keys: settings (for each name: source "saved", "env" or "default", is_secret, kind, is_set, and for
   *   the ones that are not secret, value and default) and is_saved. The keys themselves are never given.
   */
  public function getServiceSettings(): array {
    return $this->run(['get'], 'manage_service_settings.py');
  }

  /**
   * Saves the service settings. The values go to the tool's input, never on its command line.
   *
   * @param array $values
   *   Name to new value. An empty key keeps the one in use.
   * @param string[] $remove
   *   Keys to clear.
   */
  public function saveServiceSettings(array $values, array $remove): array {
    $input = json_encode(['values' => $values, 'remove' => array_values($remove)], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
    $result = $this->run(['set'], 'manage_service_settings.py', $input);
    // Only which keys changed is logged, never a key.
    $changedKeys = array_keys(array_filter($values, static fn ($value, $name) => in_array($name, ['gemini_api_key', 'api_bible_key', 'recaptcha_secret_key'], TRUE) && $value !== '', ARRAY_FILTER_USE_BOTH));
    $this->logger->notice('@user saved the service settings@keys@removed.', [
      '@user' => $this->currentUser->getAccountName(),
      '@keys' => $changedKeys ? ' (new: ' . implode(', ', $changedKeys) . ')' : '',
      '@removed' => $remove ? ' (removed: ' . implode(', ', $remove) . ')' : '',
    ]);
    return $result;
  }

  /**
   * The last backup or restore started from the Backup and restore page, and the backup zips waiting to be
   * saved by the browser.
   *
   * @return array
   *   Keys: status (action, state, message, started_at, updated_at, and for a finished backup its files, each
   *   name and size; or NULL) and waiting (a list of name, size and part; empty when none).
   */
  public function backupStatus(): array {
    return $this->run(['status'], 'manage_backup.py');
  }

  /**
   * Deletes any backup zips still waiting, then starts building a new backup in the background: two zips for
   * the database (the Bible database and Drupal's), one for the files.
   */
  public function startBackup(bool $database, bool $files, string $note): array {
    $result = $this->run(['backup', ...$this->backupParts($database, $files), '--note=' . $note], 'manage_backup.py');
    $this->logger->notice('@user started a backup (@parts).', [
      '@user' => $this->currentUser->getAccountName(),
      '@parts' => $this->describeParts($database, $files),
    ]);
    return $result;
  }

  /**
   * Deletes one backup zip waiting on the server (once the browser has saved it), or all of them.
   */
  public function discardBackup(string $name = ''): array {
    return $this->run(['discard', '--name=' . $name], 'manage_backup.py');
  }

  /**
   * Starts restoring the uploaded backup zips (one or more of one backup) in the background.
   *
   * @param string[] $names
   *   The names of the zips as chosen on the administrator's computer, for the log.
   */
  public function startRestore(array $names): array {
    // Logged before it starts: restoring Drupal's database replaces it, this log included.
    $this->logger->warning('@user started restoring a backup (@names).', [
      '@user' => $this->currentUser->getAccountName(),
      '@names' => implode(', ', $names),
    ]);
    return $this->run(['restore'], 'manage_backup.py');
  }

  /**
   * Forgets the last finished backup or restore, so the page stops showing it.
   */
  public function clearBackupStatus(): void {
    $this->run(['clear-status'], 'manage_backup.py');
  }

  /**
   * The folder the backup tool works in (ml-service/data/backup): outgoing/ holds the zips waiting to be
   * saved, incoming/upload-0.zip, upload-1.zip ... the zips being uploaded to restore.
   */
  public function backupWorkDirectory(): string {
    return $this->mlDirectory() . '/data/backup';
  }

  private function backupParts(bool $database, bool $files): array {
    return array_merge($database ? ['--database'] : [], $files ? ['--files'] : []);
  }

  private function describeParts(bool $database, bool $files): string {
    return implode(' and ', array_merge($database ? ['database'] : [], $files ? ['files'] : []));
  }

  /**
   * The main site's accounts (its visitors, not Drupal users), newest first, 50 at a time.
   *
   * @param string $query
   *   Keeps only the accounts whose address or name contains this.
   * @param int $page
   *   The page, from 1.
   *
   * @return array
   *   Keys: users (each with id, email, first_name, last_name, phone, created_at, last_login_at,
   *   email_verified, open_ai_queries, use_conversations, see_private_prayers, note_count and subscription_count; the names and phone are '' when
   *   the account has none), total, page and per_page.
   */
  public function listSiteUsers(string $query, int $page, string $sort = 'name', string $direction = 'asc'): array {
    return $this->run(['list', '--query=' . $query, '--page=' . $page, '--sort=' . $sort, '--direction=' . $direction], 'manage_users.py');
  }

  public function getSiteUser(int $userId): array {
    return $this->run(['get', '--id=' . $userId], 'manage_users.py')['user'];
  }

  /**
   * Adds an account to the main site. The password is passed on the tool's input, never as an argument.
   *
   * @param array $profile
   *   first_name, last_name and phone (each may be '').
   */
  public function createSiteUser(string $email, string $password, bool $emailVerified, bool $openAiQueries, bool $useConversations, bool $seePrivatePrayers, array $profile, bool $useMaps = FALSE, bool $phoneVerified = FALSE, bool $shareLists = FALSE, bool $getConversationPosts = FALSE, bool $texts = FALSE): array {
    // An empty $email: the account logs in with its phone (profile phone), confirmed when $phoneVerified.
    $arguments = ['create', '--email=' . $email, ...$this->profileArguments($profile), '--password-on-input'];
    if ($phoneVerified) {
      $arguments[] = '--phone-verified';
    }
    if ($emailVerified) {
      $arguments[] = '--email-verified';
    }
    if ($openAiQueries) {
      $arguments[] = '--open-ai-queries';
    }
    if ($useConversations) {
      $arguments[] = '--use-conversations';
    }
    if ($seePrivatePrayers) {
      $arguments[] = '--see-private-prayers';
    }
    if ($useMaps) {
      $arguments[] = '--use-maps';
    }
    if ($shareLists) {
      $arguments[] = '--share-lists';
    }
    if ($getConversationPosts) {
      $arguments[] = '--get-conversation-posts';
    }
    if ($texts) {
      $arguments[] = '--texts';
    }
    $user = $this->run($arguments, 'manage_users.py', $password . "\n")['user'];
    $this->logger->notice('@user added the site account @email.', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $user['email'] ?: $user['phone'],
    ]);
    return $user;
  }

  /**
   * Changes an account of the main site. An empty password keeps the old one; a new one logs it out everywhere.
   *
   * @param array $profile
   *   first_name, last_name and phone; an empty one clears it.
   */
  public function updateSiteUser(int $userId, string $email, string $password, bool $emailVerified, bool $openAiQueries, bool $useConversations, bool $seePrivatePrayers, array $profile, bool $useMaps = FALSE, ?bool $closed = NULL, ?bool $phoneVerified = NULL, ?bool $shareLists = NULL, ?bool $getConversationPosts = NULL, ?bool $texts = NULL, ?int $drupalUid = NULL): array {
    $before = $closed === NULL && $texts === NULL ? NULL : $this->getSiteUser($userId);
    $arguments = [
      'update',
      '--id=' . $userId,
      '--email=' . $email,
      ...$this->profileArguments($profile),
      '--email-verified=' . ($emailVerified ? 'yes' : 'no'),
      '--open-ai-queries=' . ($openAiQueries ? 'yes' : 'no'),
      '--use-conversations=' . ($useConversations ? 'yes' : 'no'),
      '--see-private-prayers=' . ($seePrivatePrayers ? 'yes' : 'no'),
      '--use-maps=' . ($useMaps ? 'yes' : 'no'),
    ];
    if ($closed !== NULL) {
      $arguments[] = '--closed=' . ($closed ? 'yes' : 'no');
    }
    if ($phoneVerified !== NULL) {
      $arguments[] = '--phone-verified=' . ($phoneVerified ? 'yes' : 'no');
    }
    if ($shareLists !== NULL) {
      $arguments[] = '--share-lists=' . ($shareLists ? 'yes' : 'no');
    }
    if ($getConversationPosts !== NULL) {
      $arguments[] = '--get-conversation-posts=' . ($getConversationPosts ? 'yes' : 'no');
    }
    if ($texts !== NULL) {
      $arguments[] = '--texts=' . ($texts ? 'yes' : 'no');
    }
    if ($drupalUid !== NULL) {
      // The Drupal administrator account it belongs to (0: none, matched by email address).
      $arguments[] = '--drupal-uid=' . max(0, $drupalUid);
    }
    $input = NULL;
    if ($password !== '') {
      $arguments[] = '--password-on-input';
      $input = $password . "\n";
    }
    $user = $this->run($arguments, 'manage_users.py', $input)['user'];
    $this->logger->notice('@user changed the site account @email@password.', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $user['email'] ?: $user['phone'],
      '@password' => $password !== '' ? ' (new password)' : '',
    ]);
    if ($before !== NULL && !empty($before['sms_opt_in']) !== !empty($user['sms_opt_in'])) {
      $this->logger->notice('@user turned texts @change for the site account @email.', [
        '@user' => $this->currentUser->getAccountName(),
        '@change' => !empty($user['sms_opt_in']) ? 'on' : 'off',
        '@email' => $user['email'] ?: $user['phone'],
      ]);
    }
    if ($before !== NULL && $closed !== NULL && !empty($before['closed']) !== !empty($user['closed'])) {
      $this->logger->notice('@user @change the site account @email.', [
        '@user' => $this->currentUser->getAccountName(),
        '@change' => !empty($user['closed']) ? 'closed' : 'reopened',
        '@email' => $user['email'] ?: $user['phone'],
      ]);
    }
    return $user;
  }

  /**
   * The tool's options for an account's name and phone. They are never written to the log.
   */
  private function profileArguments(array $profile): array {
    return [
      '--first-name=' . ($profile['first_name'] ?? ''),
      '--last-name=' . ($profile['last_name'] ?? ''),
      '--phone=' . ($profile['phone'] ?? ''),
    ];
  }

  /**
   * Deletes an account of the main site, with its notes and email subscriptions.
   */
  public function deleteSiteUser(int $userId): array {
    $user = $this->run(['delete', '--id=' . $userId], 'manage_users.py')['user'];
    $this->logger->notice('@user deleted the site account @email (@notes notes).', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $user['email'] ?: $user['phone'],
      '@notes' => $user['note_count'],
    ]);
    return $user;
  }

  /**
   * The members' posts of Conversations, newest first, for the admin page.
   *
   * @return array
   *   Keys: posts (each with id, title, body, excerpt, created_at, updated_at, author, author_email and
   *   reply_count), total,
   *   page and per_page.
   */
  public function listConversationPosts(string $query, int $page, string $board = ''): array {
    $arguments = ['list', '--query=' . $query, '--page=' . $page];
    if (in_array($board, ['conversations', 'prayer'], TRUE)) {
      $arguments[] = '--board=' . $board;
    }
    return $this->run($arguments, 'manage_conversations.py');
  }

  /**
   * One post with its replies (each with id, body, excerpt, created_at, updated_at, author and author_email).
   */
  public function getConversationPost(int $postId): array {
    return $this->run(['get', '--id=' . $postId], 'manage_conversations.py')['post'];
  }

  public function getConversationReply(int $replyId): array {
    return $this->run(['get-reply', '--id=' . $replyId], 'manage_conversations.py')['reply'];
  }

  /**
   * Removes any member's reply. The log says who removed it, on which post and whose it was, never its text.
   */
  public function deleteConversationReply(int $replyId): array {
    $reply = $this->run(['delete-reply', '--id=' . $replyId], 'manage_conversations.py')['reply'];
    $this->logger->notice('@user deleted a reply by @email to the Conversations post "@title".', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $reply['author_email'],
      '@title' => $reply['post_title'],
    ]);
    return $reply;
  }

  /**
   * Removes any member's post with its replies. The log says who removed which post and whose it was, never its
   * text.
   */
  public function deleteConversationPost(int $postId): array {
    $post = $this->run(['delete', '--id=' . $postId], 'manage_conversations.py')['post'];
    $this->logger->notice('@user deleted the Conversations post "@title" by @email (@replies replies).', [
      '@user' => $this->currentUser->getAccountName(),
      '@title' => $post['title'],
      '@email' => $post['author_email'],
      '@replies' => count($post['replies'] ?? []),
    ]);
    return $post;
  }

  /**
   * Largest song file, in bytes (music.MAX_FILE_BYTES). The server's own limits (PHP and nginx) must allow it.
   */
  public const MAX_MUSIC_BYTES = 1024 * 1024 * 1024;

  /**
   * Every song of the Christian music section, hidden ones too, by title.
   *
   * @return array
   *   Each song has id, title, author, lyrics, kind ("audio" or "video"), file_size, file_present,
   *   is_published, created_at and updated_at.
   */
  public function listMusic(): array {
    return $this->run(['list'], 'manage_music.py')['songs'];
  }

  public function getMusic(string $songId): array {
    return $this->run(['get', '--id=' . $songId], 'manage_music.py')['song'];
  }

  /**
   * Saves a song: a new song or a new file for one ($file), else only its details, and its words file (a PDF
   * or picture shown below the typed words) when one is given or removed. The uploaded files wait in
   * the private upload folder only while the tool copies them, and are removed afterwards whatever happens.
   *
   * @param array $details
   *   title, author and lyrics, sent on the tool's input (the words can be long).
   */
  public function saveMusic(string $songId, array $details, ?UploadedFile $file, ?UploadedFile $wordsFile = NULL, bool $removeWords = FALSE, ?UploadedFile $wordsDocument = NULL): array {
    $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    try {
      $arguments = $file !== NULL ? ['upload'] : ['update', '--id=' . $songId];
      if ($file !== NULL) {
        $extension = strtolower($file->getClientOriginalExtension());
        $file->move($directory, 'upload.' . $extension);
        $arguments = ['upload', $directory . '/upload.' . $extension, '--name=upload.' . $extension, '--id=' . $songId];
      }
      if ($wordsFile !== NULL) {
        $extension = strtolower($wordsFile->getClientOriginalExtension());
        $wordsFile->move($directory, 'words.' . $extension);
        $arguments[] = '--words=' . $directory . '/words.' . $extension;
        $arguments[] = '--words-name=words.' . $extension;
      }
      elseif ($removeWords && $file === NULL) {
        $arguments[] = '--remove-words';
      }
      // A PDF or Word document whose text becomes the words, with its formatting.
      if ($wordsDocument !== NULL) {
        $extension = strtolower($wordsDocument->getClientOriginalExtension());
        $wordsDocument->move($directory, 'words-document.' . $extension);
        $arguments[] = '--words-document=' . $directory . '/words-document.' . $extension;
        $arguments[] = '--words-document-name=words-document.' . $extension;
      }
      $input = json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
      $song = $this->run($arguments, 'manage_music.py', $input)['song'];
      // A new song file with its words file removed: upload keeps the words file, so remove it next.
      if ($file !== NULL && $wordsFile === NULL && $removeWords) {
        $song = $this->run(['update', '--id=' . $songId, '--remove-words'], 'manage_music.py', $input)['song'];
      }
    }
    finally {
      $this->fileSystem->deleteRecursive($directory);
    }
    $this->logMusic($file !== NULL ? 'uploaded' : 'changed', $song);
    return $song;
  }

  /**
   * Adds a Spotify item (no file: a Spotify link, shown with Spotify's embedded player) or changes one.
   *
   * @param array $details
   *   spotify_link (a Spotify link or URI, checked by the ML service), title, author, keywords and lyrics.
   */
  public function saveSpotifyMusic(string $songId, array $details, bool $isNew): array {
    $input = json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
    $song = $this->run([$isNew ? 'spotify' : 'update', '--id=' . $songId], 'manage_music.py', $input)['song'];
    $this->logMusic($isNew ? 'added the Spotify item' : 'changed', $song);
    return $song;
  }

  /**
   * Publishes, hides or deletes a song (deleting removes its file), or removes its PDF or picture of the words.
   */
  public function changeMusic(string $action, string $songId): array {
    if (!in_array($action, ['publish', 'unpublish', 'delete', 'remove-words'], TRUE)) {
      throw new BibleManagerException('Unknown action.');
    }
    $song = $this->run([$action, '--id=' . $songId], 'manage_music.py')['song'];
    $this->logMusic(match ($action) {
      'publish' => 'published',
      'unpublish' => 'hid',
      'remove-words' => 'removed the PDF or picture of the words of',
      default => 'deleted',
    }, $song);
    return $song;
  }

  private function logMusic(string $change, array $song): void {
    $this->logger->notice('@user @change the song “@title” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@title' => $song['title'],
      '@id' => $song['id'],
    ]);
  }

  /**
   * Largest map file, in bytes (maps.MAX_FILE_BYTES).
   */
  public const MAX_MAP_BYTES = 1024 * 1024 * 1024;

  /**
   * The extensions a map may have: pictures and PDFs (maps.FILE_TYPES).
   */
  public const MAP_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'tif', 'tiff', 'pdf'];

  /**
   * Every map, hidden ones too, by title.
   *
   * @return array
   *   Each map has id, title, description, source, keywords, verses_text, verses, kind ("image" or "pdf"),
   *   file_type, file_size, pdf_page, width, height, file_present and is_published.
   */
  public function listMaps(): array {
    return $this->run(['list'], 'manage_maps.py')['maps'];
  }

  /**
   * One map, with mark_count (the members' notes, pins and routes on it).
   */
  public function getMap(string $mapId): array {
    return $this->run(['get', '--id=' . $mapId], 'manage_maps.py')['map'];
  }

  /**
   * Saves a map: a new map or a new file for one ($file), else only its details (and, for a PDF, the page
   * drawn as the map). The uploaded file waits in the private upload folder only while the tool reads it.
   *
   * @param array $details
   *   title, description, source and, when given, keywords and verses; sent on the tool's input.
   */
  public function saveMap(string $mapId, array $details, ?UploadedFile $file, ?int $pdfPage = NULL): array {
    $input = json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
    if ($file === NULL) {
      $arguments = ['update', '--id=' . $mapId];
      if ($pdfPage !== NULL) {
        $arguments[] = '--page=' . $pdfPage;
      }
      // Drawing another page of a PDF may take a while.
      $map = $this->run($arguments, 'manage_maps.py', $input, self::DOCUMENT_TIMEOUT_SECONDS);
    }
    else {
      $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
      if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
        throw new BibleManagerException('The upload could not be saved.');
      }
      try {
        $extension = strtolower($file->getClientOriginalExtension());
        $file->move($directory, 'upload.' . $extension);
        $arguments = ['upload', $directory . '/upload.' . $extension, '--name=upload.' . $extension, '--id=' . $mapId, '--page=' . ($pdfPage ?? 1)];
        $map = $this->run($arguments, 'manage_maps.py', $input, self::DOCUMENT_TIMEOUT_SECONDS);
      }
      finally {
        $this->fileSystem->deleteRecursive($directory);
      }
    }
    $this->logMap($file !== NULL ? 'uploaded' : 'changed', $map['map']);
    return $map['map'];
  }

  /**
   * The verses typed for a map, read as the site reads them; throws with a message naming any not understood.
   */
  public function checkMapVerses(string $verses): array {
    return $this->run(['check-verses'], 'manage_maps.py', json_encode(['verses' => $verses], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE))['verses'];
  }

  /**
   * Publishes, hides or deletes a map (deleting removes its files and the members' marks on it).
   */
  public function changeMap(string $action, string $mapId): array {
    if (!in_array($action, ['publish', 'unpublish', 'delete'], TRUE)) {
      throw new BibleManagerException('Unknown action.');
    }
    $map = $this->run([$action, '--id=' . $mapId], 'manage_maps.py')['map'];
    $this->logMap(match ($action) {
      'publish' => 'published',
      'unpublish' => 'hid',
      default => 'deleted',
    }, $map);
    return $map;
  }

  private function logMap(string $change, array $map): void {
    $this->logger->notice('@user @change the map “@title” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@title' => $map['title'],
      '@id' => $map['id'],
    ]);
  }

  /**
   * The groups this user may see: their own (Group leader), or every group (with "administer groups").
   */
  public function listGroups(): array {
    $arguments = ['list'];
    if (!$this->currentUser->hasPermission('administer groups')) {
      $arguments[] = '--owner=' . (int) $this->currentUser->id();
    }
    return $this->run($arguments, 'manage_groups.py')['groups'];
  }

  /**
   * Whether this user may see and message a group: its leader, or anyone who administers all groups.
   */
  public function mayManageGroup(array $group): bool {
    return (int) $group['owner_uid'] === (int) $this->currentUser->id() || $this->currentUser->hasPermission('administer groups');
  }

  /**
   * One group with its members and latest messages. Throws if this user may not manage it.
   */
  public function getGroup(int $groupId): array {
    $group = $this->run(['get', '--group=' . $groupId], 'manage_groups.py')['group'];
    if (!$this->mayManageGroup($group)) {
      throw new BibleManagerException('That group is not one of yours.');
    }
    return $group;
  }

  /**
   * Makes a group (led by this user) or changes one's name and description. $leader, from someone who may
   * administer all groups, moves the group to that Drupal user (who must be able to lead groups): its emails'
   * Reply-To becomes their address.
   */
  public function saveGroup(?int $groupId, string $name, string|array $description, ?AccountInterface $leader = NULL): array {
    $owner = $this->currentUser;
    $previous = NULL;
    if ($groupId !== NULL) {
      $previous = $this->getGroup($groupId);
    }
    $moving = $leader !== NULL && $previous !== NULL && (int) $leader->id() !== (int) $previous['owner_uid'];
    if ($moving) {
      if (!$this->currentUser->hasPermission('administer groups')) {
        throw new BibleManagerException('Only those who administer all groups can change a group\'s leader.');
      }
      if (!$leader->hasPermission('lead groups') && !$leader->hasPermission('administer groups')) {
        throw new BibleManagerException('That person cannot lead groups: give them the Group leader role first.');
      }
      $owner = $leader;
    }
    $arguments = ['save', '--owner=' . ($previous !== NULL && !$moving ? (int) $previous['owner_uid'] : (int) $owner->id())];
    if ($groupId !== NULL) {
      $arguments[] = '--group=' . $groupId;
    }
    if ($moving) {
      $arguments[] = '--set-owner';
    }
    // The leader's name and address (the Reply-To) are refreshed from the leader's own account: the new leader's,
    // or the current user's when they lead the group; an administrator editing someone else's group keeps the
    // leader's as they are.
    $ownerName = $owner->getDisplayName();
    $ownerEmail = (string) $owner->getEmail();
    if ($previous !== NULL && !$moving && (int) $previous['owner_uid'] !== (int) $this->currentUser->id()) {
      $ownerName = $previous['owner_name'];
      $ownerEmail = $previous['owner_email'];
    }
    // $description: plain text, or ['html' => ...] from the editor / ['text' => ...] from the plain box
    // (GroupEditor::value); the ML service cleans the HTML.
    $notes = is_array($description) ? $description : ['text' => $description];
    $group = $this->run($arguments, 'manage_groups.py', $this->groupInput([
      'name' => $name,
      'description' => $notes['text'] ?? '',
      'description_html' => $notes['html'] ?? NULL,
      'owner_name' => $ownerName,
      'owner_email' => $ownerEmail,
    ]))['group'];
    $this->logGroup($groupId === NULL ? 'made' : 'changed', $group);
    if ($moving) {
      $this->logger->notice('@user made @leader the leader of the group “@name” (@id), instead of @before.', [
        '@user' => $this->currentUser->getAccountName(),
        '@leader' => $leader->getAccountName(),
        '@name' => $group['name'],
        '@id' => $group['id'],
        '@before' => $previous['owner_name'],
      ]);
    }
    return $group;
  }

  public function deleteGroup(int $groupId): array {
    $this->getGroup($groupId);
    $group = $this->run(['delete', '--group=' . $groupId], 'manage_groups.py')['group'];
    $this->logGroup('deleted', $group);
    return $group;
  }

  /**
   * Adds a member by address: the site account with it, else a contact with the name (and phone) given.
   */
  public function addGroupMember(int $groupId, array $details): array {
    $group = $this->getGroup($groupId);
    $member = $this->run(['add-member', '--group=' . $groupId], 'manage_groups.py', $this->groupInput($details))['member'];
    $this->logGroup('added a member to', $group);
    return $member;
  }

  /**
   * The site's accounts not in the group yet (id, name, email, confirmed), for the Add a member list.
   */
  public function listGroupCandidates(int $groupId): array {
    $this->getGroup($groupId);
    return $this->run(['candidates', '--group=' . $groupId], 'manage_groups.py')['accounts'];
  }

  /**
   * Adds the site accounts ticked in the list. Returns the members added.
   */
  public function addGroupAccounts(int $groupId, array $userIds): array {
    $group = $this->getGroup($groupId);
    $members = $this->run(['add-accounts', '--group=' . $groupId], 'manage_groups.py', $this->groupInput(['user_ids' => array_values($userIds)]))['members'];
    $this->logger->notice('@user added @count site accounts to the group “@name” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@count' => count($members),
      '@name' => $group['name'],
      '@id' => $group['id'],
    ]);
    return $members;
  }

  public function updateGroupMember(int $groupId, int $memberId, array $details): array {
    $group = $this->getGroup($groupId);
    $member = $this->run(['update-member', '--group=' . $groupId, '--member=' . $memberId], 'manage_groups.py', $this->groupInput($details))['member'];
    $this->logGroup('changed a member of', $group);
    return $member;
  }

  /**
   * A member's stopped scheduled emails start again (the group page's undo). Returns the member.
   */
  public function restartGroupMemberSchedules(int $groupId, int $memberId): array {
    $group = $this->getGroup($groupId);
    $member = $this->run(['restart-schedules', '--group=' . $groupId, '--member=' . $memberId], 'manage_groups.py')['member'];
    $this->logger->notice('@user started the scheduled emails again for member @member of the group “@name” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@member' => $member['id'],
      '@name' => $group['name'],
      '@id' => $group['id'],
    ]);
    return $member;
  }

  public function removeGroupMember(int $groupId, int $memberId): array {
    $group = $this->getGroup($groupId);
    $member = $this->run(['remove-member', '--group=' . $groupId, '--member=' . $memberId], 'manage_groups.py')['member'];
    $this->logGroup('removed a member from', $group);
    return $member;
  }

  /**
   * Emails the leader's words to one member of the group only (the Email link in the member list). Returns the
   * member's id and name. Throws if this user may not manage the group, or the member stopped the group's
   * messages or has not confirmed their address.
   */
  /**
   * An email to one member of a group: now, or (with $sendAt: on_date Y-m-d, send_time H:i, timezone) kept as a
   * one-time scheduled email to that member (the "Send at" field, 2026-11-18). Returns the member, and the
   * schedule under 'schedule' when it was kept for later.
   */
  public function emailGroupMember(int $groupId, int $memberId, array $message, ?array $sendAt = NULL): array {
    $group = $this->getGroup($groupId);
    // $message: html (from the editor; the ML service cleans it) or text (the plain box).
    // subject: the box's Subject (the ML service checks it, and uses its own wording when it is empty).
    // signature_id: one of the leader's signatures, or '' for none (the ML service checks it is the leader's).
    $details = array_intersect_key($message, ['html' => TRUE, 'text' => TRUE, 'subject' => TRUE, 'signature_id' => TRUE]);
    $details['sent_by'] = $this->currentUser->getAccountName();
    if ($sendAt !== NULL) {
      $details += array_intersect_key($sendAt, ['on_date' => TRUE, 'send_time' => TRUE, 'timezone' => TRUE]);
    }
    $answer = $this->run(['email-member', '--group=' . $groupId, '--member=' . $memberId], 'manage_groups.py', $this->groupInput($details));
    $member = $answer['member'];
    $this->logger->notice($sendAt === NULL
      ? '@user emailed member @member of the group “@name” (@id).'
      : '@user scheduled an email to member @member of the group “@name” (@id).', [
        '@user' => $this->currentUser->getAccountName(),
        '@member' => $member['id'],
        '@name' => $group['name'],
        '@id' => $group['id'],
      ]);
    if (isset($answer['schedule'])) {
      $member['schedule'] = $answer['schedule'];
    }
    return $member;
  }

  /**
   * A random well-known verse as a card: card (its saved name), image (a data: address), words, caption, verse.
   */
  /**
   * The current administrator's site account (linked on Site users, else the one with their email address) and
   * its newest saved verse cards, each with a thumbnail as a data: address: {account, cards}.
   */
  public function adminSavedCards(): array {
    return $this->run([
      'my-cards',
      '--drupal-uid=' . (int) $this->currentUser->id(),
      '--email=' . (string) $this->currentUser->getEmail(),
    ], 'manage_groups.py');
  }

  public function previewGroupVerse(): array {
    return $this->run(['preview-verse'], 'manage_groups.py')['preview'];
  }

  /**
   * The leader's words over a random verse a day picture: card, image and words.
   */
  public function previewGroupPicture(string $text): array {
    return $this->run(['preview-picture'], 'manage_groups.py', $this->groupInput(['text' => $text]))['preview'];
  }

  /**
   * Sends a message, a verse card or a picture message to every member of a group who has not stopped them.
   * Returns the counts: emailed, texted, skipped and failed. A big group takes a while (one email at a time).
   */
  public function sendToGroup(int $groupId, string $kind, array $details): array {
    $group = $this->getGroup($groupId);
    $details['sent_by'] = $this->currentUser->getAccountName();
    // A saved verse card is looked up among the cards of the person sending (their site account; saved_cards.py).
    if (!empty($details['saved_card'])) {
      $details['admin'] = ['uid' => (int) $this->currentUser->id(), 'email' => (string) $this->currentUser->getEmail()];
    }
    $counts = $this->run(['send', '--group=' . $groupId, '--kind=' . $kind], 'manage_groups.py', $this->groupInput($details), self::GROUP_SEND_TIMEOUT_SECONDS)['counts'];
    $this->logger->notice('@user sent a @kind to the group “@name” (@id): @emailed emailed, @texted texted, @skipped skipped, @failed failed.', [
      '@user' => $this->currentUser->getAccountName(),
      '@kind' => $kind,
      '@name' => $group['name'],
      '@id' => $group['id'],
      '@emailed' => $counts['emailed'],
      '@texted' => $counts['texted'],
      '@skipped' => $counts['skipped'],
      '@failed' => $counts['failed'],
    ]);
    return $counts;
  }

  /**
   * Adds a scheduled message to a group (group_schedules.py): kind, subject, text, repeat, on_date, day_of_month,
   * weekday, week_of_month, send_time ("HH:MM") and timezone. Returns it with its description and next time.
   */
  public function addGroupSchedule(int $groupId, array $details): array {
    $group = $this->getGroup($groupId);
    $details['created_by'] = $this->currentUser->getAccountName();
    $schedule = $this->run(['add-schedule', '--group=' . $groupId], 'manage_groups.py', $this->groupInput($details))['schedule'];
    $this->logSchedule('scheduled', $schedule, $group);
    return $schedule;
  }

  /**
   * The copy kept of one email sent to a group (groups.get_copy): from, to, reply_to, bcc (every address it was
   * emailed to), leader_copy, subject, html (NULL when it had none), text, and the Sent table's details. Throws
   * if this user may not manage the group, or the message has no copy (sent before copies were kept).
   */
  public function getGroupSentCopy(int $groupId, int $messageId): array {
    $this->getGroup($groupId);
    return $this->run(['sent-copy', '--group=' . $groupId, '--message=' . $messageId], 'manage_groups.py')['copy'];
  }

  public function getGroupSchedule(int $groupId, int $scheduleId): array {
    $this->getGroup($groupId);
    return $this->run(['get-schedule', '--group=' . $groupId, '--schedule=' . $scheduleId], 'manage_groups.py')['schedule'];
  }

  public function updateGroupSchedule(int $groupId, int $scheduleId, array $details): array {
    $group = $this->getGroup($groupId);
    $schedule = $this->run(['update-schedule', '--group=' . $groupId, '--schedule=' . $scheduleId], 'manage_groups.py', $this->groupInput($details))['schedule'];
    $this->logSchedule('changed the scheduled', $schedule, $group);
    return $schedule;
  }

  public function removeGroupSchedule(int $groupId, int $scheduleId): array {
    $group = $this->getGroup($groupId);
    $schedule = $this->run(['remove-schedule', '--group=' . $groupId, '--schedule=' . $scheduleId], 'manage_groups.py')['schedule'];
    $this->logSchedule('removed the scheduled', $schedule, $group);
    return $schedule;
  }

  /**
   * Sends a scheduled email now to the group's leader only, as a test. Returns {to, schedule}.
   */
  public function testGroupSchedule(int $groupId, int $scheduleId): array {
    $group = $this->getGroup($groupId);
    $result = $this->run(['test-schedule', '--group=' . $groupId, '--schedule=' . $scheduleId], 'manage_groups.py');
    $this->logSchedule('sent a test of the scheduled', $result['schedule'], $group);
    return $result;
  }

  private function logSchedule(string $change, array $schedule, array $group): void {
    $this->logger->notice('@user @change @kind for the group “@name” (@id): @when.', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@kind' => $schedule['kind'],
      '@name' => $group['name'],
      '@id' => $group['id'],
      '@when' => $schedule['description'],
    ]);
  }

  /**
   * A send to a whole group: up to 500 members, one email at a time.
   */
  private const GROUP_SEND_TIMEOUT_SECONDS = 600;

  private function groupInput(array $details): string {
    return json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
  }

  private function logGroup(string $change, array $group): void {
    $this->logger->notice('@user @change the group “@name” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@name' => $group['name'],
      '@id' => $group['id'],
    ]);
  }

  /**
   * Whether this user may see and change a signature or task: the one who made it, or anyone who administers
   * all signatures and tasks.
   */
  public function mayManageSignatureOrTask(array $item): bool {
    return (int) $item['owner_uid'] === (int) $this->currentUser->id() || $this->currentUser->hasPermission('administer signatures and tasks');
  }

  /**
   * The owner argument of a list: this user's own, unless they administer all signatures and tasks.
   */
  private function ownerArguments(): array {
    return $this->currentUser->hasPermission('administer signatures and tasks') ? [] : ['--owner=' . (int) $this->currentUser->id()];
  }

  /**
   * The signatures this user may see, by name. Each has id, name, html, text, preview, owner_uid, owner_name,
   * created_at and updated_at.
   */
  public function listSignatures(): array {
    return $this->run(['list', ...$this->ownerArguments()], 'manage_signatures.py')['signatures'];
  }

  /**
   * One signature. Throws if this user may not manage it.
   */
  public function getSignature(int $signatureId): array {
    $signature = $this->run(['get', '--id=' . $signatureId], 'manage_signatures.py')['signature'];
    if (!$this->mayManageSignatureOrTask($signature)) {
      throw new BibleManagerException('That signature is not one of yours.');
    }
    return $signature;
  }

  /**
   * Adds a signature (belonging to this user) or changes one. $words is ['html' => ...] from the editor or
   * ['text' => ...] from the plain box (GroupEditor::value); the ML service cleans the HTML.
   */
  public function saveSignature(?int $signatureId, string $name, array $words, ?int $ownerUid = NULL): array {
    $owner = $this->chosenOwner($ownerUid);
    $details = ['name' => $name, 'signature' => $words, 'owner_name' => ($owner ?? $this->currentUser)->getDisplayName()];
    if ($signatureId === NULL) {
      $signature = $this->run(['create', '--owner=' . (int) ($owner ?? $this->currentUser)->id()], 'manage_signatures.py', $this->groupInput($details))['signature'];
      $this->logSignatureOrTask('added', 'signature', $signature);
      return $signature;
    }
    $previous = $this->getSignature($signatureId);
    $moving = $owner !== NULL && (int) $owner->id() !== (int) $previous['owner_uid'];
    if ($moving) {
      $details += ['new_owner_uid' => (int) $owner->id(), 'new_owner_name' => $owner->getDisplayName()];
    }
    $signature = $this->run(['update', '--id=' . $signatureId], 'manage_signatures.py', $this->groupInput($details))['signature'];
    $this->logSignatureOrTask($moving ? 'moved to ' . $owner->getAccountName() . ' and changed' : 'changed', 'signature', $signature);
    return $signature;
  }

  /**
   * The owner an administrator chose for a signature or task (the Owner select), or NULL when none was chosen.
   * Only those who administer signatures and tasks may choose one, and only someone who may keep them.
   */
  private function chosenOwner(?int $ownerUid): ?AccountInterface {
    if ($ownerUid === NULL || $ownerUid === (int) $this->currentUser->id()) {
      return $ownerUid === NULL ? NULL : $this->currentUser;
    }
    if (!$this->currentUser->hasPermission('administer signatures and tasks')) {
      throw new BibleManagerException('Only those who administer signatures and tasks can choose their owner.');
    }
    $owner = SignatureTaskOwners::load($ownerUid);
    if ($owner === NULL || !SignatureTaskOwners::mayOwn($owner)) {
      throw new BibleManagerException('That person cannot keep signatures and tasks: give them a role that can first.');
    }
    return $owner;
  }

  public function deleteSignature(int $signatureId): array {
    $this->getSignature($signatureId);
    $signature = $this->run(['delete', '--id=' . $signatureId], 'manage_signatures.py')['signature'];
    $this->logSignatureOrTask('deleted', 'signature', $signature);
    return $signature;
  }

  /**
   * The tasks this user may see, by name. Each has id, name, description_html/_text, repeat, weekday,
   * first_date, day_of_month, how_often (in words), next_date, first_notification_html/_text,
   * second_notification_html/_text, preview, owner_uid, owner_name, created_at and updated_at.
   */
  public function listTasks(): array {
    return $this->run(['list', ...$this->ownerArguments()], 'manage_tasks.py')['tasks'];
  }

  /**
   * One task. Throws if this user may not manage it.
   */
  public function getTask(int $taskId): array {
    $task = $this->run(['get', '--id=' . $taskId], 'manage_tasks.py')['task'];
    if (!$this->mayManageSignatureOrTask($task)) {
      throw new BibleManagerException('That task is not one of yours.');
    }
    return $task;
  }

  /**
   * Adds a task (belonging to this user) or changes one.
   *
   * @param array $details
   *   name, repeat (weekly, biweekly or monthly), weekday (0 Monday to 6 Sunday), first_date (Y-m-d),
   *   day_of_month (1 to 31), first_notice_days and second_notice_days (0 to 90, or NULL), and description,
   *   first_notification and second_notification, each ['html' => ...] or ['text' => ...] (GroupEditor::value).
   */
  public function saveTask(?int $taskId, array $details): array {
    $previous = $taskId === NULL ? NULL : $this->getTask($taskId);
    // An administrator's Owner choice (2026-11-23): who makes the task, or who it moves to.
    $owner = $this->chosenOwner(isset($details['owner_uid']) ? (int) $details['owner_uid'] : NULL);
    unset($details['owner_uid']);
    $moving = $owner !== NULL && $previous !== NULL && (int) $owner->id() !== (int) $previous['owner_uid'];
    $account = $owner ?? $this->currentUser;
    $details += ['owner_name' => $account->getDisplayName()];
    // The reminders go at 8:00 AM in the owner's time zone, with replies to the owner: taken from the owner's own
    // account when they save it, or when it is made for or moved to someone (an administrator changing someone
    // else's task otherwise leaves them as they are).
    $timezone = fn (AccountInterface $person) => $person->getTimeZone() ?: (string) \Drupal::config('system.date')->get('timezone.default');
    if ($previous === NULL || $moving || (int) $previous['owner_uid'] === (int) $this->currentUser->id()) {
      $details['timezone'] = $timezone($moving || $previous === NULL ? $account : $this->currentUser);
      $details['owner_email'] = (string) ($moving || $previous === NULL ? $account : $this->currentUser)->getEmail();
    }
    if ($moving) {
      $details += ['new_owner_uid' => (int) $owner->id(), 'new_owner_name' => $owner->getDisplayName()];
    }
    $input = $this->groupInput($details);
    if ($taskId === NULL) {
      $task = $this->run(['create', '--owner=' . (int) $account->id()], 'manage_tasks.py', $input)['task'];
    }
    else {
      $task = $this->run(['update', '--id=' . $taskId], 'manage_tasks.py', $input)['task'];
    }
    $this->logSignatureOrTask($taskId === NULL ? 'added' : ($moving ? 'moved to ' . $owner->getAccountName() . ' and changed' : 'changed'), 'task', $task);
    return $task;
  }

  public function deleteTask(int $taskId): array {
    $this->getTask($taskId);
    $task = $this->run(['delete', '--id=' . $taskId], 'manage_tasks.py')['task'];
    $this->logSignatureOrTask('deleted', 'task', $task);
    return $task;
  }

  /**
   * What the Schedule form offers for a task this user may see: task, dates (its next four, each value Y-m-d and
   * label) and users (the site's open accounts, each id and label).
   */
  public function taskScheduleOptions(int $taskId): array {
    $this->getTask($taskId);
    return $this->run(['schedule-options', '--id=' . $taskId], 'manage_tasks.py');
  }

  /**
   * What Schedule tasks offers for a date (Y-m-d): on_date, label, tasks (this user's, or everyone's for an
   * administrator, that fall on it; each id, name, owner_uid, owner_name and scheduled_for, who has it already) and
   * users (the site's open accounts).
   */
  public function taskDayOptions(string $onDate): array {
    return $this->run(['day-options', '--date=' . $onDate, ...$this->ownerArguments()], 'manage_tasks.py');
  }

  /**
   * Message a day (day_messages.py): the dates from today on with something scheduled (value, label, people), the
   * people of one date (id, label, tasks), and sending a message to the people chosen. Each limited to the tasks
   * this user may see.
   */
  public function dayMessageDates(): array {
    return $this->run(['day-dates', ...$this->ownerArguments()], 'manage_tasks.py')['dates'];
  }

  public function dayMessagePeople(string $onDate): array {
    return $this->run(['day-people', '--date=' . $onDate, ...$this->ownerArguments()], 'manage_tasks.py')['people'];
  }

  /**
   * Returns sent ([label, how]) and not_sent ([label, why]). The log names the date and how many, never who.
   */
  public function sendDayMessage(string $onDate, array $userIds, string $subject, array $message, string $signatureId, array $files = [], bool $showSentBy = TRUE): array {
    $input = $this->groupInput([
      'on_date' => $onDate,
      'user_ids' => array_values($userIds),
      'subject' => $subject,
      'message' => $message,
      'signature_id' => $signatureId,
      'sender_name' => $this->currentUser->getDisplayName(),
      'sender_email' => (string) $this->currentUser->getEmail(),
      'show_sent_by' => $showSentBy,
    ]);
    // The attachments wait in the private upload folder only while the tool reads them (it keeps its own copies).
    $arguments = ['send-day-message', '--by=' . (int) $this->currentUser->id(), ...$this->ownerArguments()];
    $directory = NULL;
    if ($files) {
      $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
      if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
        throw new BibleManagerException('The attachments could not be saved.');
      }
    }
    try {
      foreach (array_values($files) as $number => $file) {
        $file->move($directory, 'attachment-' . $number);
        $arguments[] = '--attachment=' . $directory . '/attachment-' . $number;
        $arguments[] = '--attachment-name=' . $file->getClientOriginalName();
      }
      $result = $this->run($arguments, 'manage_tasks.py', $input);
    }
    finally {
      if ($directory !== NULL) {
        $this->fileSystem->deleteRecursive($directory);
      }
    }
    $this->logger->notice('@user sent a message to the people scheduled on @date (@files attached): @sent sent, @missed not sent.', [
      '@files' => count($files),
      '@user' => $this->currentUser->getAccountName(),
      '@date' => $onDate,
      '@sent' => count($result['sent']),
      '@missed' => count($result['not_sent']),
    ]);
    return $result;
  }

  /**
   * Schedules several tasks on one date at once: $items are [task_id, user_id, note => [text]]. All or none.
   * Returns the scheduled tasks made, each logged like Schedule.
   */
  public function addScheduledTasks(string $onDate, array $items): array {
    $input = $this->groupInput(['on_date' => $onDate, 'items' => $items, 'created_by_name' => $this->currentUser->getDisplayName()]);
    $schedules = $this->run(['add-schedules', '--by=' . (int) $this->currentUser->id(), ...$this->ownerArguments()], 'manage_tasks.py', $input)['schedules'];
    foreach ($schedules as $schedule) {
      $this->logScheduledTask('scheduled', $schedule);
    }
    return $schedules;
  }

  /**
   * The scheduled tasks of the tasks this user may see, by date. Each has id, task_id, task_name, owner_uid,
   * owner_name, user_id, user_label, on_date (Y-m-d), past, created_by_name, created_at and updated_at.
   */
  public function listScheduledTasks(): array {
    return $this->run(['schedules', ...$this->ownerArguments()], 'manage_tasks.py')['schedules'];
  }

  /**
   * One scheduled task. Throws if this user may not see its task.
   */
  public function getScheduledTask(int $scheduleId): array {
    $schedule = $this->run(['get-schedule', '--schedule=' . $scheduleId], 'manage_tasks.py')['schedule'];
    if (!$this->mayManageSignatureOrTask($schedule)) {
      throw new BibleManagerException('That scheduled task is not one of yours.');
    }
    return $schedule;
  }

  /**
   * Gives a task to a site user on one of its next four dates (Y-m-d).
   */
  public function addScheduledTask(int $taskId, int $userId, string $onDate, array $note = []): array {
    $this->getTask($taskId);
    $input = $this->groupInput(['user_id' => $userId, 'on_date' => $onDate, 'note' => $note, 'created_by_name' => $this->currentUser->getDisplayName()]);
    $schedule = $this->run(['add-schedule', '--id=' . $taskId, '--by=' . (int) $this->currentUser->id()], 'manage_tasks.py', $input)['schedule'];
    $this->logScheduledTask('scheduled', $schedule);
    return $schedule;
  }

  public function updateScheduledTask(int $scheduleId, int $userId, string $onDate, array $note = []): array {
    $this->getScheduledTask($scheduleId);
    $input = $this->groupInput(['user_id' => $userId, 'on_date' => $onDate, 'note' => $note]);
    $schedule = $this->run(['update-schedule', '--schedule=' . $scheduleId], 'manage_tasks.py', $input)['schedule'];
    $this->logScheduledTask('changed the schedule of', $schedule);
    return $schedule;
  }

  public function removeScheduledTask(int $scheduleId): array {
    $this->getScheduledTask($scheduleId);
    $schedule = $this->run(['remove-schedule', '--schedule=' . $scheduleId], 'manage_tasks.py')['schedule'];
    $this->logScheduledTask('removed the schedule of', $schedule);
    return $schedule;
  }

  /**
   * The log names the task, the date and the account's number, never the person's name or address.
   */
  private function logScheduledTask(string $change, array $schedule): void {
    $this->logger->notice('@user @change the task “@task” (@id) for site user @account on @date.', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@task' => $schedule['task_name'],
      '@id' => $schedule['task_id'],
      '@account' => $schedule['user_id'],
      '@date' => $schedule['on_date'],
    ]);
  }

  /**
   * The signatures of a group's leader, or of a task's owner (pass ['owner_uid' => ...]), for a Signature select.
   * $group comes from getGroup or getTask, which have checked that this user may manage it.
   */
  public function listLeaderSignatures(array $group): array {
    return $this->run(['list', '--owner=' . (int) $group['owner_uid']], 'manage_signatures.py')['signatures'];
  }

  /**
   * The external sites (external_sites.py), by name: id, name, address, host, notes, created_by, created_at and
   * updated_at.
   */
  /**
   * The Kindle books of the Devotionals ("devotionals") or the Other books ("books"): links to Amazon's Kindle web
   * reader with an optional picture (kindle_books.py).
   */
  public function listKindleBooks(string $collection): array {
    return $this->run(['list', '--collection=' . $collection], 'manage_kindle_books.py')['books'];
  }

  /**
   * One Kindle book, with its picture as a data: address (cover_data_uri) for a preview.
   */
  public function getKindleBook(int $bookId): array {
    return $this->run(['get', '--id=' . $bookId], 'manage_kindle_books.py')['book'];
  }

  public function saveKindleBook(?int $bookId, string $collection, string $title, string $author, string $address, bool $published): array {
    $input = $this->groupInput(['collection' => $collection, 'title' => $title, 'author' => $author, 'address' => $address, 'is_published' => $published, 'created_by' => $this->currentUser->getAccountName()]);
    $book = $bookId === NULL
      ? $this->run(['create'], 'manage_kindle_books.py', $input)['book']
      : $this->run(['update', '--id=' . $bookId], 'manage_kindle_books.py', $input)['book'];
    $this->logKindleBook($bookId === NULL ? 'added' : 'changed', $book);
    return $book;
  }

  public function deleteKindleBook(int $bookId): array {
    $book = $this->run(['delete', '--id=' . $bookId], 'manage_kindle_books.py')['book'];
    $this->logKindleBook('deleted', $book);
    return $book;
  }

  /**
   * Replaces a Kindle book's picture with an uploaded file, which waits in the private upload folder only while the
   * tool copies it.
   */
  public function saveKindleCover(int $bookId, UploadedFile $file): array {
    $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    try {
      $extension = strtolower($file->getClientOriginalExtension());
      $file->move($directory, 'cover.' . $extension);
      $book = $this->run(
        ['cover', '--id=' . $bookId, '--file=' . $directory . '/cover.' . $extension, '--name=cover.' . $extension],
        'manage_kindle_books.py',
      )['book'];
    }
    finally {
      $this->fileSystem->deleteRecursive($directory);
    }
    $this->logKindleBook('replaced the picture of', $book);
    return $book;
  }

  public function removeKindleCover(int $bookId): array {
    $book = $this->run(['remove-cover', '--id=' . $bookId], 'manage_kindle_books.py')['book'];
    $this->logKindleBook('removed the picture of', $book);
    return $book;
  }

  private function logKindleBook(string $change, array $book): void {
    $this->logger->notice('@user @change the Kindle book “@title” (@collection).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@title' => $book['title'],
      '@collection' => $book['collection'],
    ]);
  }

  public function listExternalSites(): array {
    return $this->run(['list'], 'manage_external_sites.py')['sites'];
  }

  public function getExternalSite(int $siteId): array {
    return $this->run(['get', '--id=' . $siteId], 'manage_external_sites.py')['site'];
  }

  /**
   * Adds a site or changes one, with its optional sign-in page and whether the public sidebar lists it (name and link
   * only). The ML service keeps only http(s) addresses.
   */
  public function saveExternalSite(?int $siteId, string $name, string $address, string $notes, string $signInAddress = '', bool $showOnSite = TRUE): array {
    $input = $this->groupInput(['name' => $name, 'address' => $address, 'notes' => $notes, 'sign_in_address' => $signInAddress, 'show_on_site' => $showOnSite, 'created_by' => $this->currentUser->getAccountName()]);
    $site = $siteId === NULL
      ? $this->run(['create'], 'manage_external_sites.py', $input)['site']
      : $this->run(['update', '--id=' . $siteId], 'manage_external_sites.py', $input)['site'];
    $this->logExternalSite($siteId === NULL ? 'added' : 'changed', $site);
    return $site;
  }

  public function deleteExternalSite(int $siteId): array {
    $site = $this->run(['delete', '--id=' . $siteId], 'manage_external_sites.py')['site'];
    $this->logExternalSite('deleted', $site);
    return $site;
  }

  private function logExternalSite(string $change, array $site): void {
    $this->logger->notice('@user @change the external site “@name” (@host).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@name' => $site['name'],
      '@host' => $site['host'],
    ]);
  }

  private function logSignatureOrTask(string $change, string $kind, array $item): void {
    $this->logger->notice('@user @change the @kind “@name” (@id) of @owner.', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@kind' => $kind,
      '@name' => $item['name'],
      '@id' => $item['id'],
      '@owner' => $item['owner_name'],
    ]);
  }

  /**
   * Largest verse a day picture, in bytes (verse_images.MAX_FILE_BYTES).
   */
  public const MAX_VERSE_IMAGE_BYTES = 25 * 1024 * 1024;

  /**
   * The extensions a verse a day picture may have (verse_images.EXTENSIONS).
   */
  public const VERSE_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp'];

  /**
   * Every verse a day picture, newest first.
   *
   * @return array
   *   Each has id, title, file_name, media_type, file_size, width, height, in_use, created_at, file_present
   *   and thumbnail (a data: address, or NULL).
   */
  public function listVerseImages(): array {
    return $this->run(['list'], 'manage_verse_images.py')['images'];
  }

  /**
   * One verse a day picture (without its thumbnail).
   */
  public function getVerseImage(string $imageId): array {
    return $this->run(['get', '--id=' . $imageId], 'manage_verse_images.py')['image'];
  }

  /**
   * Saves an uploaded picture as a new verse a day picture, in use at once. The file waits in the private
   * upload folder only while the tool copies it.
   */
  public function saveVerseImage(string $imageId, string $title, UploadedFile $file): array {
    $directory = $this->uploadRoot() . '/' . bin2hex(random_bytes(16));
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    try {
      $extension = strtolower($file->getClientOriginalExtension());
      $file->move($directory, 'upload.' . $extension);
      $image = $this->run(
        ['upload', $directory . '/upload.' . $extension, '--name=upload.' . $extension, '--id=' . $imageId, '--title=' . $title],
        'manage_verse_images.py',
      )['image'];
    }
    finally {
      $this->fileSystem->deleteRecursive($directory);
    }
    $this->logVerseImage('uploaded', $image);
    return $image;
  }

  /**
   * Puts a picture back in use, takes it out of use (kept, never chosen) or deletes it with its files.
   */
  public function changeVerseImage(string $action, string $imageId): array {
    if (!in_array($action, ['use', 'unuse', 'delete'], TRUE)) {
      throw new BibleManagerException('Unknown action.');
    }
    $image = $this->run([$action, '--id=' . $imageId], 'manage_verse_images.py')['image'];
    $this->logVerseImage(match ($action) {
      'use' => 'put in use',
      'unuse' => 'took out of use',
      default => 'deleted',
    }, $image);
    return $image;
  }

  private function logVerseImage(string $change, array $image): void {
    $this->logger->notice('@user @change the verse a day picture “@title” (@id).', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@title' => $image['title'],
      '@id' => $image['id'],
    ]);
  }

  /**
   * The FAQ questions, grouped as on the FAQ page: each group has heading and questions (number, question).
   */
  public function listFaqQuestions(): array {
    return $this->run(['questions'], 'manage_faq_notes.py')['groups'];
  }

  /**
   * The site's FAQ list for the FAQ questions page: source ("site", or "built-in" while it has none of its own),
   * about (the words about who the site is for, sent to Gemini) and groups (heading, questions: id, question).
   */
  public function getFaqQuestionList(): array {
    $result = $this->run(['list'], 'manage_faq_questions.py');
    return ['source' => $result['source'], 'about' => $result['about'], 'groups' => $result['groups']];
  }

  public function getFaqQuestion(int $questionId): array {
    return $this->run(['get', '--id=' . $questionId], 'manage_faq_questions.py')['question'];
  }

  /**
   * Adds a question (NULL id) or changes one: its heading and wording. Rewording moves its note with it.
   */
  public function saveFaqQuestion(?int $questionId, string $heading, string $question): array {
    $input = json_encode(['heading' => $heading, 'question' => $question], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
    $saved = $questionId === NULL
      ? $this->run(['add'], 'manage_faq_questions.py', $input)['question']
      : $this->run(['update', '--id=' . $questionId], 'manage_faq_questions.py', $input)['question'];
    $this->logFaqQuestion($questionId === NULL ? 'added' : 'changed', $saved['question']);
    return $saved;
  }

  public function deleteFaqQuestion(int $questionId): array {
    $deleted = $this->run(['delete', '--id=' . $questionId], 'manage_faq_questions.py')['question'];
    $this->logFaqQuestion('deleted', $deleted['question']);
    return $deleted;
  }

  public function moveFaqQuestion(int $questionId, string $direction): array {
    return $this->run(['move', '--id=' . $questionId, '--direction=' . $direction], 'manage_faq_questions.py')['question'];
  }

  /**
   * The words about who the site is for, added to Gemini's instructions for every FAQ answer (plain text).
   */
  public function saveFaqAbout(string $about): string {
    $saved = $this->run(['about'], 'manage_faq_questions.py', json_encode(['about' => $about], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE))['about'];
    $this->logger->notice('@user changed the words about the site sent with the FAQ questions.', ['@user' => $this->currentUser->getAccountName()]);
    return $saved;
  }

  /**
   * Back to the FAQ list built into the site, with no words about the site.
   */
  public function useBuiltInFaqQuestions(): void {
    $this->run(['built-in'], 'manage_faq_questions.py');
    $this->logger->notice('@user went back to the built-in FAQ questions.', ['@user' => $this->currentUser->getAccountName()]);
  }

  private function logFaqQuestion(string $change, string $question): void {
    $this->logger->notice('@user @change the FAQ question “@question”.', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@question' => $question,
    ]);
  }

  /**
   * The site owner's notes on the FAQ answers, in the order of their questions.
   *
   * @return array
   *   Each note has id, question, question_number (NULL when the question is no longer on the FAQ),
   *   is_listed, html, preview (the start of its text), created_at and updated_at.
   */
  public function listFaqNotes(): array {
    return $this->run(['list'], 'manage_faq_notes.py')['notes'];
  }

  public function getFaqNote(int $noteId): array {
    return $this->run(['get', '--id=' . $noteId], 'manage_faq_notes.py')['note'];
  }

  /**
   * Adds a note. It is sent on the tool's input (it can be long); the log names the question, not the text.
   */
  public function createFaqNote(string $question, string $html): array {
    $note = $this->run(['create'], 'manage_faq_notes.py', $this->faqNoteInput($question, $html))['note'];
    $this->logFaqNote('added', $note);
    return $note;
  }

  public function updateFaqNote(int $noteId, string $question, string $html): array {
    $note = $this->run(['update', '--id=' . $noteId], 'manage_faq_notes.py', $this->faqNoteInput($question, $html))['note'];
    $this->logFaqNote('changed', $note);
    return $note;
  }

  public function deleteFaqNote(int $noteId): array {
    $note = $this->run(['delete', '--id=' . $noteId], 'manage_faq_notes.py')['note'];
    $this->logFaqNote('deleted', $note);
    return $note;
  }

  private function faqNoteInput(string $question, string $html): string {
    return json_encode(['question' => $question, 'html' => $html], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
  }

  private function logFaqNote(string $change, array $note): void {
    $this->logger->notice('@user @change the FAQ note on “@question”.', [
      '@user' => $this->currentUser->getAccountName(),
      '@change' => $change,
      '@question' => $note['question'],
    ]);
  }

  /**
   * Keeps an uploaded file, and what the administrator typed, until they confirm or cancel.
   *
   * @return string
   *   A random token that names the upload.
   */
  public function storeUpload(UploadedFile $file, array $parameters): string {
    $token = bin2hex(random_bytes(16));
    $directory = $this->uploadRoot() . '/' . $token;
    if (!mkdir($directory, 0700, TRUE) && !is_dir($directory)) {
      throw new BibleManagerException('The upload could not be saved.');
    }
    // The tool tells a PDF or Word document from text by the extension, so it is kept.
    $extension = strtolower($file->getClientOriginalExtension());
    $file->move($directory, 'upload.' . (in_array($extension, self::UPLOAD_EXTENSIONS, TRUE) ? $extension : 'txt'));
    $this->writeJson($directory . '/meta.json', [
      'uid' => (int) $this->currentUser->id(),
      'created' => time(),
      'parameters' => $parameters,
    ]);
    return $token;
  }

  /**
   * The stored upload, or NULL if there is none with this token.
   *
   * @return array|null
   *   Keys: path, meta (uid, created, parameters) and preview (or NULL).
   */
  public function loadUpload(string $token): ?array {
    $directory = $this->uploadDirectory($token);
    $path = NULL;
    foreach ($directory === NULL ? [] : self::UPLOAD_EXTENSIONS as $extension) {
      if (is_file($directory . '/upload.' . $extension)) {
        $path = $directory . '/upload.' . $extension;
        break;
      }
    }
    if ($path === NULL || !is_file($directory . '/meta.json')) {
      return NULL;
    }
    $meta = json_decode((string) file_get_contents($directory . '/meta.json'), TRUE);
    if (!is_array($meta)) {
      return NULL;
    }
    $preview = is_file($directory . '/preview.json')
      ? json_decode((string) file_get_contents($directory . '/preview.json'), TRUE)
      : NULL;
    return [
      'path' => $path,
      'meta' => $meta,
      'preview' => is_array($preview) ? $preview : NULL,
    ];
  }

  public function savePreview(string $token, array $preview): void {
    $directory = $this->uploadDirectory($token);
    if ($directory !== NULL) {
      $this->writeJson($directory . '/preview.json', $preview);
    }
  }

  public function removeUpload(string $token): void {
    $directory = $this->uploadDirectory($token);
    if ($directory !== NULL) {
      $this->fileSystem->deleteRecursive($directory);
    }
  }

  public function removeStaleUploads(): void {
    try {
      $root = $this->uploadRoot();
    }
    catch (BibleManagerException) {
      return;
    }
    foreach (glob($root . '/*', GLOB_ONLYDIR) ?: [] as $directory) {
      if (preg_match(self::TOKEN_PATTERN, basename($directory)) && filemtime($directory) < time() - self::STALE_UPLOAD_SECONDS) {
        $this->fileSystem->deleteRecursive($directory);
      }
    }
  }

  /**
   * Arguments for a preview or an import.
   *
   * Values are joined to their option with "=" so that a value starting with "-" can never be
   * taken for an option.
   */
  private function fileArguments(string $path, array $parameters): array {
    $arguments = [
      $path,
      '--code=' . $parameters['code'],
      '--name=' . $parameters['name'],
      '--license=' . $parameters['license'],
      '--language=' . $parameters['language'],
      '--format=' . ($parameters['format'] ?: 'auto'),
    ];
    if (!empty($parameters['source_url'])) {
      $arguments[] = '--source-url=' . $parameters['source_url'];
    }
    if (!empty($parameters['strip_brackets'])) {
      $arguments[] = '--strip-brackets';
    }
    if (!empty($parameters['skip_unmatched_books'])) {
      $arguments[] = '--skip-unmatched-books';
    }
    return $arguments;
  }

  /**
   * Runs one of the Python tools and returns its JSON answer.
   *
   * @param string|null $input
   *   Sent to the tool's standard input (a password, so it never shows in the process list).
   */
  private function run(array $arguments, string $tool = 'manage_bibles.py', ?string $input = NULL, ?int $timeout = NULL): array {
    $directory = $this->mlDirectory();
    $python = $directory . '/.venv/bin/python';
    $script = $directory . '/scripts/' . $tool;
    foreach ([$python, $script] as $required) {
      if (!is_file($required)) {
        throw new BibleManagerException('The Bible tools are not installed on this server.');
      }
    }

    // A PDF or Word document (an upload or a song's words document) may take longer to read.
    $timeout ??= preg_grep('/\.(pdf|docx|epub)$/i', $arguments) ? self::DOCUMENT_TIMEOUT_SECONDS : self::COMMAND_TIMEOUT_SECONDS;
    $process = new Process([$python, $script, ...$arguments], $directory, NULL, $input, $timeout);
    try {
      $process->run();
    }
    catch (ProcessTimedOutException) {
      throw new BibleManagerException('The importer took too long and was stopped. Nothing was saved.');
    }

    $result = json_decode($process->getOutput(), TRUE);
    if (!is_array($result)) {
      $this->logger->error('The Bible importer gave no usable answer. Error output: @output', [
        '@output' => substr($process->getErrorOutput(), 0, 2000),
      ]);
      throw new BibleManagerException('The importer gave an unexpected answer. The details are in the Drupal log.');
    }
    if (empty($result['ok'])) {
      throw new BibleManagerException((string) ($result['error'] ?? 'The importer failed.'));
    }
    return $result;
  }

  /**
   * Where the Python code lives. The default fits the layout of the repository.
   */
  private function mlDirectory(): string {
    $configured = Settings::get('bible_admin_ml_directory');
    $directory = realpath($configured ?: DRUPAL_ROOT . '/../../ml-service');
    if ($directory === FALSE) {
      throw new BibleManagerException('The Bible importer folder was not found on this server.');
    }
    return $directory;
  }

  private function uploadRoot(): string {
    $uri = 'private://' . self::UPLOAD_FOLDER;
    if (!$this->fileSystem->prepareDirectory($uri, FileSystemInterface::CREATE_DIRECTORY)) {
      throw new BibleManagerException('The private upload folder is not available.');
    }
    $root = $this->fileSystem->realpath($uri);
    if ($root === FALSE) {
      throw new BibleManagerException('The private upload folder is not available.');
    }
    return $root;
  }

  /**
   * The folder for a token, or NULL if the token is malformed or has no folder.
   */
  private function uploadDirectory(string $token): ?string {
    if (!preg_match(self::TOKEN_PATTERN, $token)) {
      return NULL;
    }
    $directory = $this->uploadRoot() . '/' . $token;
    return is_dir($directory) ? $directory : NULL;
  }

  private function writeJson(string $path, array $data): void {
    file_put_contents($path, json_encode($data, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE), LOCK_EX);
    chmod($path, 0600);
  }

}
