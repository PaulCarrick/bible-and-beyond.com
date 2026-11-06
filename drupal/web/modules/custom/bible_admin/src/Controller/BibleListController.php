<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The list of Bibles in the search database.
 */
class BibleListController extends ControllerBase {

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
        '#value' => $this->t('These are the Bibles in the search database. Only published Bibles appear on the public search page. A newly uploaded Bible stays hidden until you publish it. The NIV, NASB and The Message come from API.Bible and are not listed here.'),
      ],
    ];

    try {
      $translations = $this->manager->listTranslations();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($translations as $translation) {
      $code = $translation['code'];
      $links = [
        $translation['is_published']
          ? ['title' => $this->t('Hide'), 'url' => Url::fromRoute('bible_admin.change', ['action' => 'unpublish', 'code' => $code])]
          : ['title' => $this->t('Publish'), 'url' => Url::fromRoute('bible_admin.change', ['action' => 'publish', 'code' => $code])],
        ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.change', ['action' => 'delete', 'code' => $code])],
      ];
      $rows[] = [
        ['data' => ['#plain_text' => $code]],
        ['data' => ['#plain_text' => $translation['name']]],
        ['data' => ['#plain_text' => $translation['language']]],
        ['data' => ['#plain_text' => $translation['license']]],
        ['data' => ['#plain_text' => number_format((int) $translation['verse_count'])]],
        ['data' => ['#plain_text' => $translation['is_published'] ? $this->t('Published') : $this->t('Hidden')]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Code'),
        $this->t('Name'),
        $this->t('Language'),
        $this->t('License'),
        $this->t('Verses'),
        $this->t('Status'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $this->t('There are no Bibles in the search database.'),
    ];
    return $build;
  }

}
