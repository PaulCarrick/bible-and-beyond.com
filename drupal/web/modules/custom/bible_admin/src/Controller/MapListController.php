<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The maps, with Publish or Hide, Edit and Delete for each.
 */
class MapListController extends ControllerBase {

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
        '#value' => $this->t('The maps of the Maps section: a picture (PNG, JPEG, WebP, GIF or TIFF) or a page of a PDF each, with its title, description, where it came from, keywords and the Bible verses it goes with. A new map is hidden until you publish it; the section appears on the site once a map is published. Only upload maps that are in the public domain or that you have permission to publish. The files are kept in the maps folder (ml-service/data/maps).'),
      ],
      // Several files at once, each a new map named after its file (js/bulk-upload.js).
      'bulk' => BulkUploadController::area('maps'),
    ];

    try {
      $maps = $this->manager->listMaps();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($maps as $map) {
      $change = fn (string $action) => Url::fromRoute('bible_admin.map_change', ['action' => $action, 'map_id' => $map['id']]);
      $links = [
        $map['is_published']
          ? ['title' => $this->t('Hide'), 'url' => $change('unpublish')]
          : ['title' => $this->t('Publish'), 'url' => $change('publish')],
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.map_edit', ['map_id' => $map['id']])],
        ['title' => $this->t('Delete'), 'url' => $change('delete')],
      ];
      $status = $map['is_published'] ? $this->t('Published') : $this->t('Hidden');
      if (!$map['file_present']) {
        $status = $this->t('@status. The file is missing from the maps folder.', ['@status' => $status]);
      }
      $kind = $map['kind'] === 'pdf'
        ? $this->t('PDF, page @page', ['@page' => $map['pdf_page']])
        : $map['file_type'];
      $rows[] = [
        ['data' => ['#markup' => $this->t('@title<br><small>Link: /maps?map=@id</small>', ['@title' => $map['title'], '@id' => $map['id']])]],
        ['data' => ['#plain_text' => $map['verses_text']]],
        ['data' => ['#plain_text' => $map['keywords']]],
        ['data' => ['#plain_text' => (string) $kind]],
        ['data' => ['#plain_text' => $map['width'] . ' × ' . $map['height']]],
        ['data' => ['#plain_text' => number_format($map['file_size'] / 1048576, 1) . ' MB']],
        ['data' => ['#plain_text' => (string) $status]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Title'),
        $this->t('Verses'),
        $this->t('Keywords'),
        $this->t('Kind'),
        $this->t('Pixels shown'),
        $this->t('Size'),
        $this->t('Status'),
        ['data' => $this->t('Operations'), 'data-no-sort' => 'true'],
      ],
      '#rows' => $rows,
      // Click a header to sort by it (js/sortable-table.js): again to reverse, a third time to clear.
      '#attributes' => ['class' => ['bible-admin-sortable']],
      '#attached' => ['library' => ['bible_admin/sortable_table']],
      '#empty' => $this->t('There are no maps yet. Use "Upload a map" to add one.'),
    ];
    return $build;
  }

}
