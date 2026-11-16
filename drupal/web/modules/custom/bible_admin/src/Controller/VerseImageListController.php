<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The verse a day pictures (verse_images.py): a drop area for one or many, then each with its thumbnail,
 * "Take out of use" or "Put in use", and Delete. Nothing here is shown on the site.
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
      $preview = $image['thumbnail']
        ? ['#type' => 'html_tag', '#tag' => 'img', '#attributes' => ['src' => $image['thumbnail'], 'alt' => '', 'width' => 120, 'loading' => 'lazy', 'style' => 'height:auto;display:block;']]
        : ['#plain_text' => '—'];
      $rows[] = [
        ['data' => $preview],
        ['data' => ['#markup' => $this->t('@title<br><small>@id</small>', ['@title' => $image['title'], '@id' => $image['id']])]],
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
      '#attributes' => ['class' => ['bible-admin-sortable']],
      '#attached' => ['library' => ['bible_admin/sortable_table']],
      '#empty' => $this->t('There are no pictures yet. Drop some on the box above.'),
    ];
    return $build;
  }

}
