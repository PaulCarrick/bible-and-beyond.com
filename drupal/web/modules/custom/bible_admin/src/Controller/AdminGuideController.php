<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\Component\Serialization\Yaml;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Render\Markup;

/**
 * The Admin guide (/admin/guide; the owner's request, 2026-11-16: "do the same thing for the admin site ... go
 * through all the screens we added ... and document them"): the screens of this module, one section each, with a
 * screenshot, in the style of the public site's Help page.
 *
 * The words are in help/admin-guide.yml and the pictures in help/images/ (WebP), so the guide is changed there,
 * not here. Each section names the permissions that let someone use its screen ("permissions", any one of them);
 * a section is shown only to those who have one, so a Group leader sees only what a Group leader can do. A
 * picture is written in the words as <img data-guide="name" alt="..."> and becomes a link to the full-size
 * picture.
 */
class AdminGuideController extends ControllerBase {

  public function build(): array {
    $directory = $this->moduleHandler()->getModule('bible_admin')->getPath() . '/help';
    $guide = Yaml::decode((string) file_get_contents($directory . '/admin-guide.yml'));
    $imageBase = base_path() . $directory . '/images/';
    $account = $this->currentUser();

    $sections = array_filter($guide['sections'], function (array $section) use ($account) {
      $permissions = $section['permissions'] ?? [];
      if (!$permissions) {
        return TRUE;
      }
      foreach ($permissions as $permission) {
        if ($account->hasPermission($permission)) {
          return TRUE;
        }
      }
      return FALSE;
    });

    $contents = '';
    $body = '';
    foreach ($sections as $section) {
      $id = 'guide-' . $section['id'];
      $contents .= '<li><a href="#' . $id . '">' . htmlspecialchars($section['title']) . '</a></li>';
      // The words are this module's own (a file in the repository), so they are used as written; pictures become
      // links to their full size.
      $html = preg_replace_callback(
        '/<img data-guide="([a-z0-9-]+)"([^>]*)>/',
        fn (array $match) => '<a class="admin-guide-picture" href="' . $imageBase . $match[1] . '.webp"><img src="' . $imageBase . $match[1] . '.webp" loading="lazy"' . $match[2] . '></a>',
        (string) $section['body'],
      );
      $body .= '<section id="' . $id . '" class="admin-guide-section"><h2>' . htmlspecialchars($section['title']) . '</h2>' . $html
        . '<p class="admin-guide-top"><a href="#admin-guide-contents">↑ ' . $this->t('Contents') . '</a></p></section>';
    }

    return [
      '#cache' => ['contexts' => ['user.permissions']],
      '#attached' => ['library' => ['bible_admin/admin_guide']],
      'intro' => ['#markup' => Markup::create((string) $guide['intro'])],
      'video' => ['#markup' => Markup::create($this->video($directory))],
      'contents' => [
        '#markup' => Markup::create('<nav id="admin-guide-contents" class="admin-guide-contents" aria-label="' . $this->t('Contents') . '"><h2>' . $this->t('Contents') . '</h2><ol>' . $contents . '</ol></nav>'),
      ],
      'sections' => ['#markup' => Markup::create($body)],
    ];
  }

  /**
   * The narrated tour of these pages (the owner's request, 2026-11-24), above the contents. The MP4 is not in git
   * (help/video/*.mp4 is ignored, as the public site's tutorial is): copy it to each server by hand. Without it,
   * nothing is shown. Its captions and poster are in the repository.
   */
  private function video(string $directory): string {
    if (!is_file($directory . '/video/admin-tour.mp4')) {
      return '';
    }
    $base = base_path() . $directory . '/video/';
    $version = (string) filemtime($directory . '/video/admin-tour.mp4');
    $captions = is_file($directory . '/video/admin-tour.en.vtt')
      ? '<track kind="captions" src="' . $base . 'admin-tour.en.vtt?v=' . $version . '" srclang="en" label="English">'
      : '';
    $poster = is_file($directory . '/video/admin-tour-poster.webp') ? ' poster="' . $base . 'admin-tour-poster.webp?v=' . $version . '"' : '';
    return '<section class="admin-guide-video" aria-labelledby="admin-guide-video-heading">'
      . '<h2 id="admin-guide-video-heading">' . $this->t('Tutorial video') . '</h2>'
      . '<p>' . $this->t('A narrated tour of these pages, with made-up people. Turn on captions with the CC button.') . '</p>'
      . '<video controls preload="metadata" playsinline' . $poster . '>'
      . '<source src="' . $base . 'admin-tour.mp4?v=' . $version . '" type="video/mp4">' . $captions . '</video></section>';
  }

}
