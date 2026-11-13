<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\File\FileSystemInterface;
use Drupal\Core\Logger\LoggerChannelFactoryInterface;
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
    ];
    $arguments = ['set'];
    $changed = [];
    foreach ($options as $key => $option) {
      if (array_key_exists($key, $values)) {
        $arguments[] = $option . $values[$key];
        $changed[] = $key;
      }
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
   * The last backup or restore started from the Backup and restore page, and the backup zip waiting to be
   * saved by the browser.
   *
   * @return array
   *   Keys: status (action, state, message, started_at, updated_at, and for a finished backup name and size;
   *   or NULL) and waiting (name and size, or NULL).
   */
  public function backupStatus(): array {
    return $this->run(['status'], 'manage_backup.py');
  }

  /**
   * Starts building a backup zip in the background, of the database, the files or both.
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
   * Deletes the backup zip waiting on the server (once the browser has saved it).
   */
  public function discardBackup(): array {
    return $this->run(['discard'], 'manage_backup.py');
  }

  /**
   * Starts restoring the uploaded backup zip in the background.
   */
  public function startRestore(bool $database, bool $files): array {
    // Logged before it starts: restoring the database replaces Drupal's, this log included.
    $this->logger->warning('@user started restoring a backup (@parts).', [
      '@user' => $this->currentUser->getAccountName(),
      '@parts' => $this->describeParts($database, $files),
    ]);
    return $this->run(['restore', ...$this->backupParts($database, $files)], 'manage_backup.py');
  }

  /**
   * Forgets the last finished backup or restore, so the page stops showing it.
   */
  public function clearBackupStatus(): void {
    $this->run(['clear-status'], 'manage_backup.py');
  }

  /**
   * The folder the backup tool works in (ml-service/data/backup): outgoing/ holds the zip waiting to be
   * saved, incoming/upload.zip the zip being uploaded to restore.
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
   *   email_verified, open_ai_queries, use_conversations, note_count and subscription_count; the names and phone are '' when
   *   the account has none), total, page and per_page.
   */
  public function listSiteUsers(string $query, int $page): array {
    return $this->run(['list', '--query=' . $query, '--page=' . $page], 'manage_users.py');
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
  public function createSiteUser(string $email, string $password, bool $emailVerified, bool $openAiQueries, bool $useConversations, array $profile): array {
    $arguments = ['create', '--email=' . $email, ...$this->profileArguments($profile), '--password-on-input'];
    if ($emailVerified) {
      $arguments[] = '--email-verified';
    }
    if ($openAiQueries) {
      $arguments[] = '--open-ai-queries';
    }
    if ($useConversations) {
      $arguments[] = '--use-conversations';
    }
    $user = $this->run($arguments, 'manage_users.py', $password . "\n")['user'];
    $this->logger->notice('@user added the site account @email.', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $user['email'],
    ]);
    return $user;
  }

  /**
   * Changes an account of the main site. An empty password keeps the old one; a new one logs it out everywhere.
   *
   * @param array $profile
   *   first_name, last_name and phone; an empty one clears it.
   */
  public function updateSiteUser(int $userId, string $email, string $password, bool $emailVerified, bool $openAiQueries, bool $useConversations, array $profile): array {
    $arguments = [
      'update',
      '--id=' . $userId,
      '--email=' . $email,
      ...$this->profileArguments($profile),
      '--email-verified=' . ($emailVerified ? 'yes' : 'no'),
      '--open-ai-queries=' . ($openAiQueries ? 'yes' : 'no'),
      '--use-conversations=' . ($useConversations ? 'yes' : 'no'),
    ];
    $input = NULL;
    if ($password !== '') {
      $arguments[] = '--password-on-input';
      $input = $password . "\n";
    }
    $user = $this->run($arguments, 'manage_users.py', $input)['user'];
    $this->logger->notice('@user changed the site account @email@password.', [
      '@user' => $this->currentUser->getAccountName(),
      '@email' => $user['email'],
      '@password' => $password !== '' ? ' (new password)' : '',
    ]);
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
      '@email' => $user['email'],
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
  public function listConversationPosts(string $query, int $page): array {
    return $this->run(['list', '--query=' . $query, '--page=' . $page], 'manage_conversations.py');
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
   * or picture shown in place of the typed words) when one is given or removed. The uploaded files wait in
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
   * Publishes, hides or deletes a song (deleting removes its file).
   */
  public function changeMusic(string $action, string $songId): array {
    if (!in_array($action, ['publish', 'unpublish', 'delete'], TRUE)) {
      throw new BibleManagerException('Unknown action.');
    }
    $song = $this->run([$action, '--id=' . $songId], 'manage_music.py')['song'];
    $this->logMusic(match ($action) {
      'publish' => 'published',
      'unpublish' => 'hid',
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
   * The FAQ questions, grouped as on the FAQ page: each group has heading and questions (number, question).
   */
  public function listFaqQuestions(): array {
    return $this->run(['questions'], 'manage_faq_notes.py')['groups'];
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
