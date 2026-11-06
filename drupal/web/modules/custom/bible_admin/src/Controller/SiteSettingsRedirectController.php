<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\Core\Controller\ControllerBase;
use Symfony\Component\HttpFoundation\RedirectResponse;

/**
 * Sends the old address of the search settings page to the one screen for the site's options.
 */
class SiteSettingsRedirectController extends ControllerBase {

  public function redirectToSiteSettings(): RedirectResponse {
    return $this->redirect('bible_admin.site_settings', [], [], 301);
  }

}
