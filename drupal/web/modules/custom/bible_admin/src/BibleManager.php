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
   * Largest upload, in bytes. A Bible text file is about 4.5 MB.
   */
  public const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

  private const UPLOAD_FOLDER = 'bible-uploads';

  private const COMMAND_TIMEOUT_SECONDS = 180;

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

  public function setPublished(string $code, bool $published): void {
    $this->run([$published ? 'publish' : 'unpublish', $code]);
    $this->logger->notice('@user @action @code.', [
      '@user' => $this->currentUser->getAccountName(),
      '@action' => $published ? 'published' : 'hid',
      '@code' => $code,
    ]);
  }

  public function delete(string $code): array {
    $result = $this->run(['delete', $code]);
    $this->logger->notice('@user deleted @code (@count verses).', [
      '@user' => $this->currentUser->getAccountName(),
      '@code' => $code,
      '@count' => $result['deleted_verse_count'],
    ]);
    return $result;
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
    $file->move($directory, 'upload.txt');
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
    if ($directory === NULL || !is_file($directory . '/upload.txt') || !is_file($directory . '/meta.json')) {
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
      'path' => $directory . '/upload.txt',
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
   * Runs the Python tool and returns its JSON answer.
   */
  private function run(array $arguments): array {
    $directory = $this->mlDirectory();
    $python = $directory . '/.venv/bin/python';
    $script = $directory . '/scripts/manage_bibles.py';
    foreach ([$python, $script] as $required) {
      if (!is_file($required)) {
        throw new BibleManagerException('The Bible importer is not installed on this server.');
      }
    }

    $process = new Process([$python, $script, ...$arguments], $directory, NULL, NULL, self::COMMAND_TIMEOUT_SECONDS);
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
