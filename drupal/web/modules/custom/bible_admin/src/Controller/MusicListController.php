<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The songs of the Christian music section, with Publish or Hide, Edit and Delete for each.
 */
class MusicListController extends ControllerBase {

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
        '#value' => $this->t('The songs of the Christian music section: an MP3 (sound) or MP4 (video) file each, with its title, author and words. A new song is hidden until you publish it; the section appears on the site once a song is published. Only upload recordings that are in the public domain or that you have permission to publish. The files are kept in the music folder set on the Site settings screen.'),
      ],
    ];

    try {
      $songs = $this->manager->listMusic();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($songs as $song) {
      $change = fn (string $action) => Url::fromRoute('bible_admin.music_change', ['action' => $action, 'song_id' => $song['id']]);
      $links = [
        $song['is_published']
          ? ['title' => $this->t('Hide'), 'url' => $change('unpublish')]
          : ['title' => $this->t('Publish'), 'url' => $change('publish')],
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.music_edit', ['song_id' => $song['id']])],
        ['title' => $this->t('Delete'), 'url' => $change('delete')],
      ];
      $status = $song['is_published'] ? $this->t('Published') : $this->t('Hidden');
      if (!$song['file_present']) {
        $status = $this->t('@status. The file is missing from the music folder.', ['@status' => $status]);
      }
      if ($song['words_kind'] !== NULL && !$song['words_file_present']) {
        $status = $this->t('@status. The words file is missing from the music folder.', ['@status' => $status]);
      }
      $rows[] = [
        ['data' => ['#markup' => $this->t('@title<br><small>Link: /music?song=@id</small>', ['@title' => $song['title'], '@id' => $song['id']])]],
        ['data' => ['#plain_text' => $song['author']]],
        ['data' => ['#plain_text' => $song['kind'] === 'video' ? $this->t('Video (MP4)') : $this->t('Sound (MP3)')]],
        ['data' => ['#plain_text' => number_format($song['file_size'] / 1048576, 1) . ' MB']],
        ['data' => ['#plain_text' => match (TRUE) {
          $song['words_kind'] === 'pdf' => $this->t('PDF'),
          $song['words_kind'] === 'image' => $this->t('Picture'),
          $song['lyrics'] !== '' => $this->t('Typed'),
          default => $this->t('None'),
        }]],
        ['data' => ['#plain_text' => (string) $status]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Title'),
        $this->t('Author'),
        $this->t('Kind'),
        $this->t('Size'),
        $this->t('Words'),
        $this->t('Status'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $this->t('There are no songs yet. Use "Upload a song" to add one.'),
    ];
    return $build;
  }

}
