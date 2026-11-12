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
 * server build a zip (ml-service/scripts/manage_backup.py, in the background), saves it into a folder the
 * administrator picks (js/backup.js) and has the server delete its copy; to restore, it uploads a zip a part
 * at a time, then has the server restore it.
 */
class BackupController extends ControllerBase {

  /**
   * The largest part of an upload. Under the PHP and nginx limits of the live server even before
   * install-system-config.sh raised them (16 MB).
   */
  public const CHUNK_BYTES = 8 * 1024 * 1024;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function page(): array {
    $parts = [
      'database' => [
        $this->t('Database'),
        $this->t('The Bible database (Bibles, commentaries, devotionals and books, the songs\' details, the site users with their notes and daily emails, the FAQ notes and answers, the site settings), Drupal\'s database (the administrators and Drupal\'s settings, the email server included) and the keys of the outside services.'),
      ],
      'files' => [
        $this->t('Files'),
        $this->t('The music files (songs and their words files) and Drupal\'s uploaded files.'),
      ],
    ];
    $checkboxes = '';
    foreach ($parts as $name => [$label, $description]) {
      $checkboxes .= '<div class="form-item form-type--checkbox"><input type="checkbox" class="form-checkbox form-boolean form-boolean--type-checkbox" id="backup-' . $name . '" name="' . $name . '" checked>'
        . ' <label for="backup-' . $name . '" class="form-item__label option">' . $label . '</label>'
        . '<div class="form-item__description">' . $description . '</div></div>';
    }

    $markup = '<div class="bible-backup">'
      . '<p>' . $this->t('A backup is one zip file, saved in a folder on your computer that you choose; nothing is kept on the server. Restore it here, or on a new server or container, to carry on where the site was. The zip holds the site users\' details and the service keys: keep it private.') . '</p>'
      . '<div class="bible-backup__status" role="status" aria-live="polite"></div>'
      . '<fieldset class="bible-backup__parts"><legend>' . $this->t('What to back up or restore') . '</legend>' . $checkboxes . '</fieldset>'
      . '<h2>' . $this->t('Back up') . '</h2>'
      . '<div class="form-item"><label for="backup-note" class="form-item__label">' . $this->t('Note (optional)') . '</label>'
      . '<input type="text" id="backup-note" class="form-text form-element" maxlength="200" size="60">'
      . '<div class="form-item__description">' . $this->t('A few words kept inside the zip, such as "Before moving to the new server".') . '</div></div>'
      . '<p><button type="button" class="button button--primary" data-backup="start">' . $this->t('Back up to a folder…') . '</button></p>'
      . '<p class="bible-backup__hint" data-backup="no-folder-hint" hidden>' . $this->t('This browser cannot save into a folder you choose (Chrome and Edge can), so the zip will be downloaded like any file, to your Downloads folder; move it where you keep your backups.') . '</p>'
      . '<h2>' . $this->t('Restore') . '</h2>'
      . '<p>' . $this->t('Choose a backup zip from your folder. Restoring the database replaces everything in both databases: anything added since the backup was taken is lost, and you will have to log in again with an account and password from the backup. Restoring the files copies the backup\'s music and Drupal files over the ones here. Back up first if you may want the site as it is now.') . '</p>'
      . '<p><button type="button" class="button" data-backup="choose">' . $this->t('Choose a backup zip…') . '</button>'
      . ' <input type="file" accept=".zip,application/zip" data-backup="file" hidden></p>'
      . '<div data-backup="restore-panel" hidden>'
      . '<p data-backup="chosen"></p>'
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
   * Sends the backup zip waiting on the server.
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
        'discard' => $this->answer($this->manager->discardBackup()),
        'upload' => $this->receivePart($request),
        'restore' => $this->restore($database, $files, (int) ($values['size'] ?? -1)),
        default => $this->dismiss(),
      };
    }
    catch (BibleManagerException $exception) {
      return $this->problem($exception->getMessage());
    }
  }

  /**
   * Adds one part of the zip being uploaded. The part at offset 0 starts a new upload.
   */
  private function receivePart(Request $request): JsonResponse {
    $offset = (int) $request->query->get('offset', '-1');
    $folder = $this->manager->backupWorkDirectory() . '/incoming';
    $path = $folder . '/upload.zip';
    if ($offset < 0) {
      return $this->problem('The upload was not understood.');
    }
    if ($offset === 0) {
      if (is_file($path)) {
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
      return $this->problem('The upload got out of step; choose the zip and try again.');
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

  private function restore(bool $database, bool $files, int $size): JsonResponse {
    $path = $this->manager->backupWorkDirectory() . '/incoming/upload.zip';
    clearstatcache(TRUE, $path);
    if (!is_file($path) || filesize($path) !== $size) {
      return $this->problem('The zip did not arrive whole; choose it and try again.');
    }
    return $this->answer($this->manager->startRestore($database, $files));
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
