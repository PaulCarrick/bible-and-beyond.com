<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Render\Markup;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\BinaryFileResponse;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\ResponseHeaderBag;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * The Backup and restore page. The backups are kept on the administrator's own computer: the page has the
 * server build up to three zips (the Bible database, Drupal's database, the files;
 * ml-service/scripts/manage_backup.py, in the background), saves them into a folder the administrator picks
 * (js/backup.js) and has the server delete each one once saved (one that failed stays to be saved again); to
 * restore, it uploads one or more zips of one backup, each a part at a time, then has the server restore them.
 */
class BackupController extends ControllerBase {

  /**
   * The largest part of an upload. Under the PHP and nginx limits of the live server even before
   * install-system-config.sh raised them (16 MB).
   */
  public const CHUNK_BYTES = 8 * 1024 * 1024;

  /**
   * The most zips one restore takes (the three of a backup; site_backup.MOST_UPLOADS).
   */
  public const MOST_FILES = 3;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function page(): array {
    $parts = [
      'database' => [
        $this->t('Database'),
        $this->t('Two zips: the Bible database (Bibles, commentaries, devotionals and books, the songs\' details, the site users with their notes and daily emails, the FAQ notes and answers, the site settings, and the keys of the outside services), and Drupal\'s database (the administrators and Drupal\'s settings, the email server included).'),
      ],
      'files' => [
        $this->t('Files'),
        $this->t('One zip: the music files (songs and their words files), the maps, pictures and icons, and Drupal\'s uploaded files.'),
      ],
    ];
    $checkboxes = '';
    foreach ($parts as $name => [$label, $description]) {
      $checkboxes .= '<div class="form-item form-type--checkbox"><input type="checkbox" class="form-checkbox form-boolean form-boolean--type-checkbox" id="backup-' . $name . '" name="' . $name . '" checked>'
        . ' <label for="backup-' . $name . '" class="form-item__label option">' . $label . '</label>'
        . '<div class="form-item__description">' . $description . '</div></div>';
    }

    $markup = '<div class="bible-backup">'
      . '<p>' . $this->t('A backup is up to three zip files (the Bible database, Drupal\'s database and the files), saved in a folder on your computer that you choose. Each is deleted from the server once it is saved; one that could not be saved (a network error, say) stays on the server so you can save it again, until the next backup is started. Restore them here, or on a new server or container, to carry on where the site was. The zips hold the site users\' details and the service keys: keep them private.') . '</p>'
      . '<div class="bible-backup__status" role="status" aria-live="polite"></div>'
      . '<h2>' . $this->t('Back up') . '</h2>'
      . '<fieldset class="bible-backup__parts"><legend>' . $this->t('What to back up') . '</legend>' . $checkboxes . '</fieldset>'
      . '<div class="form-item"><label for="backup-note" class="form-item__label">' . $this->t('Note (optional)') . '</label>'
      . '<input type="text" id="backup-note" class="form-text form-element" maxlength="200" size="60">'
      . '<div class="form-item__description">' . $this->t('A few words kept inside the zips, such as "Before moving to the new server".') . '</div></div>'
      . '<p><button type="button" class="button button--primary" data-backup="start">' . $this->t('Back up to a folder…') . '</button></p>'
      . '<p class="bible-backup__hint" data-backup="no-folder-hint" hidden>' . $this->t('This browser cannot save into a folder you choose (Chrome and Edge can), so the zips will be downloaded like any file, to your Downloads folder; move them where you keep your backups.') . '</p>'
      . '<h2>' . $this->t('Restore') . '</h2>'
      . '<p>' . $this->t('Choose one or more zips of one backup from your folder (hold Shift or Cmd to choose several); what they hold is restored, the rest is left as it is. Restoring the Bible database or Drupal\'s database replaces it: anything added since the backup was taken is lost, and restoring Drupal\'s database means logging in again with an account and password from the backup. Restoring the files copies the backup\'s files over the ones here. A zip made before backups were split in three holds everything and is restored whole. Back up first if you may want the site as it is now.') . '</p>'
      . '<p><button type="button" class="button" data-backup="choose">' . $this->t('Choose backup zips…') . '</button>'
      . ' <input type="file" accept=".zip,application/zip" multiple data-backup="file" hidden></p>'
      . '<div data-backup="restore-panel" hidden>'
      . '<div data-backup="chosen"></div>'
      . '<div class="form-item"><label for="backup-confirm" class="form-item__label">' . $this->t('Type RESTORE to confirm') . '</label>'
      . '<input type="text" id="backup-confirm" class="form-text form-element" size="20" autocomplete="off"></div>'
      . '<p><button type="button" class="button button--danger" data-backup="restore">' . $this->t('Restore') . '</button></p>'
      . '</div>'
      . '<div class="bible-backup__progress" data-backup="progress" hidden><progress max="100" value="0"></progress> <span></span></div>'
      . '</div>';

    return [
      // Built here from fixed text only (no user input), so it is not filtered (the filter would drop the
      // form elements and their data attributes).
      '#markup' => Markup::create($markup),
      '#cache' => ['max-age' => 0],
      '#attached' => [
        'library' => ['bible_admin/backup'],
        'drupalSettings' => [
          'bibleAdminBackup' => [
            'statusUrl' => Url::fromRoute('bible_admin.backup_status')->toString(),
            // The JSON routes are this page's address plus /{action}, and /download/{name}.
            'pageUrl' => Url::fromRoute('bible_admin.backup')->toString(),
            'tokenUrl' => Url::fromRoute('system.csrftoken')->toString(),
            'loginUrl' => Url::fromRoute('user.login', [], ['query' => ['destination' => Url::fromRoute('bible_admin.backup')->toString()]])->toString(),
            'chunkBytes' => self::CHUNK_BYTES,
            'mostFiles' => self::MOST_FILES,
          ],
        ],
      ],
    ];
  }

  public function status(): JsonResponse {
    try {
      return $this->answer($this->manager->backupStatus());
    }
    catch (BibleManagerException $exception) {
      return $this->problem($exception->getMessage());
    }
  }

  /**
   * Sends one of the backup zips waiting on the server (it stays there until the page has it deleted).
   */
  public function download(string $name): BinaryFileResponse {
    $path = $this->manager->backupWorkDirectory() . '/outgoing/' . $name;
    if (!is_file($path)) {
      throw new NotFoundHttpException();
    }
    $response = new BinaryFileResponse($path, 200, ['Content-Type' => 'application/zip', 'Cache-Control' => 'no-store'], FALSE);
    $response->setContentDisposition(ResponseHeaderBag::DISPOSITION_ATTACHMENT, $name);
    return $response;
  }

  public function act(Request $request, string $action): JsonResponse {
    try {
      $values = json_decode((string) ($action === 'upload' ? '{}' : $request->getContent()), TRUE) ?: [];
      $database = !empty($values['database']);
      $files = !empty($values['files']);
      return match ($action) {
        'start' => $this->answer($this->manager->startBackup($database, $files, mb_substr(trim((string) ($values['note'] ?? '')), 0, 200))),
        'discard' => $this->answer($this->manager->discardBackup((string) ($values['name'] ?? ''))),
        'upload' => $this->receivePart($request),
        'restore' => $this->restore($values['files'] ?? NULL),
        default => $this->dismiss(),
      };
    }
    catch (BibleManagerException $exception) {
      return $this->problem($exception->getMessage());
    }
  }

  /**
   * Adds one part of a zip being uploaded (?file=0, 1 ... and ?offset=). The part at offset 0 of the first
   * file starts a new upload, removing any zips uploaded before.
   */
  private function receivePart(Request $request): JsonResponse {
    $offset = (int) $request->query->get('offset', '-1');
    $file = (int) $request->query->get('file', '-1');
    $folder = $this->manager->backupWorkDirectory() . '/incoming';
    if ($offset < 0 || $file < 0 || $file >= self::MOST_FILES) {
      return $this->problem('The upload was not understood.');
    }
    $path = $folder . '/upload-' . $file . '.zip';
    if ($offset === 0) {
      if ($file === 0) {
        foreach (glob($folder . '/upload*.zip') ?: [] as $old) {
          unlink($old);
        }
      }
      elseif (is_file($path)) {
        unlink($path);
      }
      if (!is_dir($folder) && !mkdir($folder, 0700, TRUE)) {
        return $this->problem('The server has no room for the upload (its folder could not be made).');
      }
      touch($path);
      chmod($path, 0600);
    }
    clearstatcache(TRUE, $path);
    if (!is_file($path) || filesize($path) !== $offset) {
      return $this->problem('The upload got out of step; choose the zips and try again.');
    }
    $input = $request->getContent(TRUE);
    $output = fopen($path, 'ab');
    $written = stream_copy_to_stream($input, $output, self::CHUNK_BYTES + 1);
    fclose($output);
    if ($written === FALSE || $written > self::CHUNK_BYTES) {
      return $this->problem('A part of the upload could not be saved (is the server\'s disk full?).');
    }
    return $this->answer(['received' => $offset + $written]);
  }

  /**
   * Starts the restore once every zip has arrived whole.
   *
   * @param mixed $chosen
   *   The zips as the page sent them: a list of name and size, in upload order.
   */
  private function restore(mixed $chosen): JsonResponse {
    if (!is_array($chosen) || !$chosen || count($chosen) > self::MOST_FILES) {
      return $this->problem('Choose the zips to restore again.');
    }
    $folder = $this->manager->backupWorkDirectory() . '/incoming';
    $names = [];
    foreach (array_values($chosen) as $index => $file) {
      $path = $folder . '/upload-' . $index . '.zip';
      clearstatcache(TRUE, $path);
      if (!is_array($file) || !is_file($path) || filesize($path) !== (int) ($file['size'] ?? -1)) {
        return $this->problem('The zips did not arrive whole; choose them and try again.');
      }
      $names[] = mb_substr(preg_replace('/[^\w.\- ]/u', '', (string) ($file['name'] ?? '')), 0, 100);
    }
    // Zips left from an earlier, larger upload are not part of this one.
    for ($index = count($chosen); $index < self::MOST_FILES; $index++) {
      if (is_file($folder . '/upload-' . $index . '.zip')) {
        unlink($folder . '/upload-' . $index . '.zip');
      }
    }
    return $this->answer($this->manager->startRestore($names));
  }

  private function dismiss(): JsonResponse {
    $this->manager->clearBackupStatus();
    return $this->answer([]);
  }

  private function answer(array $result): JsonResponse {
    $response = new JsonResponse(['ok' => TRUE] + $result);
    $response->headers->set('Cache-Control', 'no-store');
    return $response;
  }

  private function problem(string $message): JsonResponse {
    return new JsonResponse(['ok' => FALSE, 'error' => $message], 400);
  }

}
