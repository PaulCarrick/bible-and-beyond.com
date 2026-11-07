<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The list of commentaries or of devotionals ({collection}), with Publish, Hide, Delete and Refresh.
 */
class LibraryListController extends ControllerBase {

  /**
   * What differs between the two collections.
   */
  public const COLLECTIONS = [
    'commentaries' => ['kind' => 'commentary', 'title' => 'Commentaries', 'one' => 'commentary', 'counted' => 'Notes', 'detail' => 'Short name'],
    'devotionals' => ['kind' => 'devotional', 'title' => 'Devotionals', 'one' => 'devotional', 'counted' => 'Readings', 'detail' => 'Author'],
    'books' => ['kind' => 'book', 'title' => 'Other books', 'one' => 'book', 'counted' => 'Chapters', 'detail' => 'Author'],
  ];

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function title(string $collection): string {
    return self::COLLECTIONS[$collection]['title'];
  }

  public function build(string $collection): array {
    $about = self::COLLECTIONS[$collection];
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => match ($collection) {
          'commentaries' => $this->t('The commentaries on the public site. A hidden one disappears from the site everywhere (the lists, search, the reader and the Commentaries window) until you publish it again. Refresh downloads one of the known commentaries again from its source (several minutes, in the background); an uploaded one is replaced by uploading its file again.'),
          'books' => $this->t('The Other books on the public site, read a chapter at a time (with no daily emails). A hidden one disappears from the site until you publish it again. Load or Refresh downloads one of the known books from Project Gutenberg in the background; an uploaded one is replaced by uploading its file again.'),
          default => $this->t('The devotionals on the public site. A hidden one disappears from the site, and its daily emails pause until you publish it again. Refresh downloads one of the known devotionals again from its source; an uploaded one is replaced by uploading its file again. Deleting one also stops its daily emails.'),
        },
      ],
      'upload' => [
        '#type' => 'link',
        '#title' => $this->t('Upload a @one', ['@one' => $about['one']]),
        '#url' => Url::fromRoute('bible_admin.library_upload', ['collection' => $collection]),
        '#attributes' => ['class' => ['button', 'button--primary', 'button--small']],
        '#prefix' => '<p>',
        '#suffix' => '</p>',
      ],
    ];

    try {
      $items = $this->manager->listLibrary($about['kind']);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $isRefreshing = FALSE;
    $rows = [];
    foreach ($items as $item) {
      $change = fn (string $action) => Url::fromRoute('bible_admin.library_change', ['collection' => $collection, 'action' => $action, 'item_id' => $item['id']]);
      $links = [];
      if ($item['loaded']) {
        $links[] = $item['is_published']
          ? ['title' => $this->t('Hide'), 'url' => $change('unpublish')]
          : ['title' => $this->t('Publish'), 'url' => $change('publish')];
      }
      $refresh = $item['refresh'];
      $running = $refresh !== NULL && in_array($refresh['state'], ['starting', 'running'], TRUE);
      $isRefreshing = $isRefreshing || $running;
      if ($item['refreshable'] && !$running) {
        $links[] = ['title' => $item['loaded'] ? $this->t('Refresh') : $this->t('Load'), 'url' => $change('refresh')];
      }
      if ($item['loaded']) {
        $links[] = ['title' => $this->t('Delete'), 'url' => $change('delete')];
      }

      $status = !$item['loaded'] ? $this->t('Not loaded') : ($item['is_published'] ? $this->t('Published') : $this->t('Hidden'));
      if ($refresh !== NULL) {
        $status = match ($refresh['state']) {
          'starting', 'running' => $this->t('@status. Refreshing: @message', ['@status' => $status, '@message' => $refresh['message']]),
          'failed' => $this->t('@status. The last refresh failed: @message', ['@status' => $status, '@message' => $refresh['message']]),
          default => $this->t('@status. @message', ['@status' => $status, '@message' => $refresh['message']]),
        };
      }
      $rows[] = [
        ['data' => ['#plain_text' => $item['name']]],
        ['data' => ['#plain_text' => $item['detail']]],
        ['data' => ['#plain_text' => $item['refreshable'] ? $item['source_name'] : $this->t('@source (uploaded)', ['@source' => $item['source_name']])]],
        ['data' => ['#plain_text' => number_format((int) $item['count'])]],
        ['data' => ['#plain_text' => (string) $status]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Name'),
        $this->t($about['detail']),
        $this->t('Source'),
        $this->t($about['counted']),
        $this->t('Status'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $this->t('There are none.'),
    ];

    // While a refresh runs, the page reloads itself every 15 seconds to show how it is going.
    if ($isRefreshing) {
      $build['#attached']['html_head'][] = [
        ['#tag' => 'meta', '#attributes' => ['http-equiv' => 'refresh', 'content' => '15']],
        'bible_admin_library_refresh',
      ];
      $build['refreshing'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('A refresh is running; this page shows its progress every 15 seconds. You can leave the page: it carries on.'),
        '#weight' => -1,
      ];
    }
    return $build;
  }

}
