<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;

/**
 * Several files at once, like the media library of the Jump Start Website: on the Christian music, Devotionals
 * and Other books pages a drop area (built by js/bulk-upload.js from area()) takes many files, and the page
 * sends them here one at a time (a song can be 1 GB, so they never share one request). Each file becomes a new
 * item named after the file, its id made from that name; an id already in use is skipped, never replaced.
 * A new item is hidden unless "Publish them when uploaded" was ticked.
 */
class BulkUploadController extends ControllerBase {

  /**
   * At most this many files in one batch.
   */
  public const MAX_FILES = 50;

  private const ID_PATTERN = '/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/';

  /**
   * What each collection takes: the extensions, the tool's kind, and the words for the page.
   */
  private const COLLECTIONS = [
    'music' => ['extensions' => ['mp3', 'mp4'], 'kind' => 'music', 'one' => 'song', 'many' => 'songs'],
    'books' => ['extensions' => ['pdf', 'docx', 'epub', 'txt', 'tsv'], 'kind' => 'book', 'one' => 'book', 'many' => 'books'],
    'devotionals' => ['extensions' => ['pdf', 'docx', 'epub', 'txt', 'tsv'], 'kind' => 'devotional', 'one' => 'devotional', 'many' => 'devotionals'],
  ];

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  /**
   * The drop area for a list page: an empty container that js/bulk-upload.js fills in (the inputs are made in
   * the browser, so no form is nested in the page).
   */
  public static function area(string $collection): array {
    $about = self::COLLECTIONS[$collection];
    return [
      '#type' => 'html_tag',
      '#tag' => 'div',
      '#value' => '',
      '#attributes' => [
        'class' => ['bible-admin-bulk-upload'],
        'data-collection' => $collection,
        'data-upload-url' => Url::fromRoute('bible_admin.bulk_upload', ['collection' => $collection])->toString(),
        'data-token-url' => Url::fromRoute('system.csrftoken')->toString(),
        'data-extensions' => implode(',', $about['extensions']),
        'data-max-files' => (string) self::MAX_FILES,
        'data-max-bytes' => (string) ($collection === 'music' ? BibleManager::MAX_MUSIC_BYTES : BibleManager::MAX_DOCUMENT_BYTES),
        'data-one' => $about['one'],
        'data-many' => $about['many'],
      ],
      '#attached' => ['library' => ['bible_admin/bulk_upload']],
    ];
  }

  /**
   * Saves one file of a batch. Answers {ok, id, name, published} or {ok: false, skipped|error}.
   */
  public function upload(Request $request, string $collection): JsonResponse {
    $about = self::COLLECTIONS[$collection];
    $file = $request->files->get('file');
    if (!$file instanceof UploadedFile || !$file->isValid()) {
      return $this->problem($file instanceof UploadedFile ? $file->getErrorMessage() : 'No file was received.');
    }
    $extension = strtolower($file->getClientOriginalExtension());
    if (in_array($extension, ['mobi', 'azw', 'azw3', 'kfx', 'prc'], TRUE)) {
      return $this->skipped('A Kindle file cannot be read here; convert an unlocked one to EPUB with Calibre first.');
    }
    if (!in_array($extension, $about['extensions'], TRUE)) {
      return $this->skipped('Not a file this page takes (' . implode(', ', array_map(fn ($each) => '.' . $each, $about['extensions'])) . ').');
    }
    $limit = $collection === 'music' ? BibleManager::MAX_MUSIC_BYTES : BibleManager::MAX_DOCUMENT_BYTES;
    if ($file->getSize() > $limit) {
      return $this->skipped('Larger than ' . (int) ($limit / 1048576) . ' MB.');
    }

    $name = self::nameOf($file->getClientOriginalName());
    $itemId = self::idOf($name);
    $options = $request->request;
    $publish = $options->get('publish') === '1';
    try {
      if ($this->idInUse($collection, $itemId)) {
        return $this->skipped('Already there (the id "' . $itemId . '" is in use), so it was left as it is.');
      }
      if ($collection === 'music') {
        $this->manager->saveMusic($itemId, ['title' => $name, 'author' => '', 'lyrics' => ''], $file);
        if ($publish) {
          $this->manager->changeMusic('publish', $itemId);
        }
      }
      else {
        $author = trim((string) $options->get('author'));
        $source = trim((string) $options->get('source_name'));
        if ($author === '' || $source === '') {
          return $this->problem('Fill in the author and where the texts came from, above the files.');
        }
        $this->manager->importLibraryUpload($file, [
          'collection' => $collection,
          'kind' => $about['kind'],
          'id' => $itemId,
          'name' => $name,
          'author' => $author,
          'source_name' => $source,
          'devotional_kind' => $collection === 'books' ? 'chapters' : ($options->get('devotional_kind') === 'daily' ? 'daily' : 'chapters'),
          'whole' => $options->get('whole') === '1',
          'keywords' => trim((string) $options->get('keywords')),
          'credit' => '',
        ]);
        if ($publish) {
          $this->manager->changeLibrary($about['kind'], 'publish', $itemId);
        }
      }
    }
    catch (BibleManagerException $exception) {
      return $this->problem($exception->getMessage());
    }
    return new JsonResponse(['ok' => TRUE, 'id' => $itemId, 'name' => $name, 'published' => $publish]);
  }

  /**
   * The item's name from its file's name: without the extension, underscores as spaces, spaces squeezed.
   */
  public static function nameOf(string $fileName): string {
    $name = preg_replace('/\.[^.]+$/', '', $fileName);
    $name = trim((string) preg_replace('/\s+/u', ' ', str_replace('_', ' ', (string) $name)));
    return mb_substr($name !== '' ? $name : 'Untitled', 0, 200);
  }

  /**
   * An id from a name: lower case, letters and digits joined by hyphens, at most 50 characters.
   */
  public static function idOf(string $name): string {
    $ascii = function_exists('iconv') ? (string) @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $name) : $name;
    $id = strtolower(str_replace('&', ' and ', $ascii));
    $id = (string) preg_replace("/['’]/", '', $id);
    $id = trim((string) preg_replace('/[^a-z0-9]+/', '-', $id), '-');
    if (strlen($id) > 50) {
      $id = rtrim(substr($id, 0, 50), '-');
    }
    if (!preg_match(self::ID_PATTERN, $id)) {
      $id = 'item-' . substr(md5($name), 0, 8);
    }
    return $id;
  }

  /**
   * Whether the id is taken: by a song, or (devotionals and books share a table) by a devotional or a book,
   * including one known to the site but not loaded yet.
   */
  private function idInUse(string $collection, string $itemId): bool {
    if ($collection === 'music') {
      $ids = array_column($this->manager->listMusic(), 'id');
    }
    else {
      $ids = [...array_column($this->manager->listLibrary('book'), 'id'), ...array_column($this->manager->listLibrary('devotional'), 'id')];
    }
    return in_array($itemId, $ids, TRUE);
  }

  private function skipped(string $reason): JsonResponse {
    return new JsonResponse(['ok' => FALSE, 'skipped' => $reason]);
  }

  private function problem(string $message): JsonResponse {
    return new JsonResponse(['ok' => FALSE, 'error' => $message]);
  }

}
