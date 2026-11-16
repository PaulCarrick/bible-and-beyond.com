<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\Access\AccessResult;
use Drupal\Core\Access\AccessResultInterface;
use Drupal\Core\Session\AccountInterface;

/**
 * Who may open a group's pages: its leader (with "lead groups"), or anyone with "administer groups".
 */
class GroupAccess {

  public static function access(AccountInterface $account, string $group_id): AccessResultInterface {
    if (!$account->hasPermission('lead groups') && !$account->hasPermission('administer groups')) {
      return AccessResult::forbidden()->cachePerPermissions();
    }
    if ($account->hasPermission('administer groups')) {
      return AccessResult::allowed()->cachePerPermissions();
    }
    try {
      // getGroup refuses a group that is not this user's.
      \Drupal::service('bible_admin.manager')->getGroup((int) $group_id);
      $allowed = TRUE;
    }
    catch (BibleManagerException) {
      $allowed = FALSE;
    }
    return AccessResult::allowedIf($allowed)->setCacheMaxAge(0);
  }

}
