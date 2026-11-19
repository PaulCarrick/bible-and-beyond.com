<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Component\Utility\Html;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The external sites (the owner's request, 2026-11-19, first for the Kindle web reader): each with an Open button that
 * opens it in its own browser window beside this one (js/external-sites.js), and Edit and Delete. Not in a frame:
 * Amazon refuses to show its sign-in inside another site, and a framed site gets none of its own cookies.
 */
class ExternalSiteListController extends ControllerBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function build(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      '#attached' => ['library' => ['bible_admin/external_sites']],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Other sites you use, such as the Kindle web reader. <strong>Open</strong> opens a site in its own window beside this one: sign in there the first time, and it stays signed in like any other tab. If the site has signed you out, sign in again in that window (its own Sign in, or the <strong>Sign in</strong> button here when the site has a sign-in address). (A site such as Amazon cannot be shown inside this page: it refuses, to protect its sign-in.) A site marked <em>Shown</em> is also listed for visitors under “External sites” in the site’s sidebar, by its name and link only.'),
      ],
    ];
    try {
      $sites = $this->manager->listExternalSites();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    $rows = [];
    foreach ($sites as $site) {
      $buttons = ['open' => $this->button((string) $this->t('Open'), $site['address'], $site, (string) $this->t('Open @name in its own window', ['@name' => $site['name']]), TRUE)];
      if ($site['sign_in_address'] !== '') {
        // Our page cannot see whether one is signed in to another site, so the way to sign in is always there.
        $buttons['sign_in'] = $this->button((string) $this->t('Sign in'), $site['sign_in_address'], $site, (string) $this->t('Open the sign-in page of @name in its window', ['@name' => $site['name']]), FALSE);
      }
      $rows[] = [
        ['data' => ['#plain_text' => $site['name']]],
        ['data' => $buttons],
        ['data' => ['#plain_text' => $site['host']]],
        ['data' => ['#plain_text' => $site['show_on_site'] ? (string) $this->t('Shown') : (string) $this->t('Not shown')]],
        ['data' => ['#markup' => nl2br(Html::escape($site['notes']), FALSE)]],
        ['data' => ['#type' => 'operations', '#links' => [
          ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.external_site_edit', ['site_id' => $site['id']])],
          ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.external_site_delete', ['site_id' => $site['id']])],
        ]]],
      ];
    }
    $build['table'] = [
      '#type' => 'table',
      '#header' => [$this->t('Name'), '', $this->t('Site'), $this->t('Sidebar'), $this->t('Notes'), $this->t('Operations')],
      '#rows' => $rows,
      '#empty' => $this->t('There are no sites yet. Use Add a site, for example the Kindle web reader at https://read.amazon.com.'),
    ];
    return $build;
  }

  /**
   * A button that opens an address in the site's own window (js/external-sites.js), or in a new tab when the
   * browser blocks the window.
   */
  private function button(string $title, string $address, array $site, string $tooltip, bool $primary): array {
    return [
      '#type' => 'link',
      '#title' => $title,
      '#url' => Url::fromUri($address),
      '#attributes' => [
        'class' => array_merge(['button', 'button--small'], $primary ? ['button--primary'] : []),
        'data-external-site' => (string) $site['id'],
        'target' => '_blank',
        'rel' => 'noopener noreferrer',
        'title' => $tooltip,
      ],
    ];
  }

}
