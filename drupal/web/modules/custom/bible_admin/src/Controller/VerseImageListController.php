<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The verse a day pictures (verse_images.py): a drop area for one or many, then each with its thumbnail,
 * "Take out of use" or "Put in use", and Delete. Nothing here is shown on the site. The pencil after a name
 * changes it in place, and a click on a thumbnail shows the picture larger in a window (js/verse-images.js).
 */
class VerseImageListController extends ControllerBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function build(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Pictures for the verse a day. They are not shown on the site: members who tick Send Multimedia Messages get the verse a day and the daily devotional written over one of these, chosen at random from those in use, in their email and picture texts. PNG, JPEG or WebP, up to @size MB each. A picture is in use as soon as it is uploaded; take it out of use to keep it without it being chosen. Only upload pictures you have the right to use. The files are kept in the verse images folder (ml-service/data/verse-images).', [
          '@size' => (int) (BibleManager::MAX_VERSE_IMAGE_BYTES / 1048576),
        ]),
      ],
      // One or many files at once, each a new picture named after its file (js/bulk-upload.js).
      'bulk' => BulkUploadController::area('verse-images'),
    ];

    try {
      $images = $this->manager->listVerseImages();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($images as $image) {
      $change = fn (string $action) => Url::fromRoute('bible_admin.verse_image_change', ['action' => $action, 'image_id' => $image['id']]);
      $links = [
        $image['in_use']
          ? ['title' => $this->t('Take out of use'), 'url' => $change('unuse')]
          : ['title' => $this->t('Put in use'), 'url' => $change('use')],
        ['title' => $this->t('Delete'), 'url' => $change('delete')],
      ];
      $status = $image['in_use'] ? $this->t('In use') : $this->t('Not in use');
      if (!$image['file_present']) {
        $status = $this->t('@status. The file is missing from the verse images folder.', ['@status' => $status]);
      }
      $thumbnail = $image['thumbnail']
        ? ['#type' => 'html_tag', '#tag' => 'img', '#attributes' => ['src' => $image['thumbnail'], 'alt' => '', 'width' => 120, 'loading' => 'lazy']]
        : ['#plain_text' => '—'];
      $preview = $image['thumbnail'] && $image['file_present']
        ? [
          '#type' => 'html_tag',
          '#tag' => 'button',
          '#attributes' => [
            'type' => 'button',
            'class' => ['verse-image-enlarge'],
            'title' => $this->t('Show this picture larger'),
            'aria-label' => $this->t('Show “@title” larger', ['@title' => $image['title']]),
            'data-preview-url' => Url::fromRoute('bible_admin.verse_image_preview', ['image_id' => $image['id']])->toString(),
          ],
          'image' => $thumbnail,
        ]
        : $thumbnail;
      $name = [
        '#type' => 'container',
        '#attributes' => [
          'class' => ['verse-image-name'],
          'data-rename-url' => Url::fromRoute('bible_admin.verse_image_rename', ['image_id' => $image['id']])->toString(),
        ],
        'title' => ['#type' => 'html_tag', '#tag' => 'span', '#attributes' => ['class' => ['verse-image-title']], '#value' => $image['title']],
        'id' => ['#type' => 'html_tag', '#tag' => 'small', '#attributes' => ['class' => ['verse-image-id']], '#value' => $image['id']],
      ];
      $rows[] = [
        ['data' => $preview],
        // Sorted by the name itself, not the pencil or the id under it (js/sortable-table.js).
        ['data' => $name, 'data-sort-value' => $image['title']],
        ['data' => ['#plain_text' => strtoupper(preg_replace('#^image/#', '', $image['media_type']))]],
        ['data' => ['#plain_text' => $image['width'] . ' × ' . $image['height']]],
        // In KB throughout, so the column sorts as numbers (js/sortable-table.js).
        ['data' => ['#plain_text' => number_format(max(1, (int) round($image['file_size'] / 1024))) . ' KB']],
        ['data' => ['#plain_text' => substr($image['created_at'], 0, 10)]],
        ['data' => ['#plain_text' => (string) $status]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        ['data' => $this->t('Picture'), 'data-no-sort' => 'true'],
        $this->t('Name'),
        $this->t('Type'),
        $this->t('Pixels'),
        $this->t('Size'),
        $this->t('Uploaded'),
        $this->t('Status'),
        ['data' => $this->t('Operations'), 'data-no-sort' => 'true'],
      ],
      '#rows' => $rows,
      // Click a header to sort by it (js/sortable-table.js): again to reverse, a third time to clear.
      '#attributes' => [
        'class' => ['bible-admin-sortable', 'verse-images-table'],
        'data-token-url' => Url::fromRoute('system.csrftoken')->toString(),
      ],
      '#attached' => ['library' => ['bible_admin/sortable_table', 'bible_admin/verse_images']],
      '#empty' => $this->t('There are no pictures yet. Drop some on the box above.'),
    ];
    return $build;
  }

  /**
   * Saves a new name typed on the list (js/verse-images.js). Answers {ok, title} or {ok: false, error}.
   */
  public function rename(Request $request, string $image_id): JsonResponse {
    try {
      $image = $this->manager->renameVerseImage($image_id, (string) $request->request->get('title', ''));
    }
    catch (BibleManagerException $exception) {
      return new JsonResponse(['ok' => FALSE, 'error' => $exception->getMessage()], 422);
    }
    return new JsonResponse(['ok' => TRUE, 'title' => $image['title']]);
  }

  /**
   * The picture's larger copy for the window opened from its thumbnail.
   */
  public function preview(string $image_id): JsonResponse {
    try {
      $image = $this->manager->previewVerseImage($image_id);
    }
    catch (BibleManagerException $exception) {
      return new JsonResponse(['ok' => FALSE, 'error' => $exception->getMessage()], 422);
    }
    $response = new JsonResponse([
      'ok' => TRUE,
      'title' => $image['title'],
      'width' => $image['width'],
      'height' => $image['height'],
      'preview' => $image['preview'],
    ]);
    $response->setPrivate();
    return $response;
  }

}
