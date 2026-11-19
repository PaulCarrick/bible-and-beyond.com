<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\Access\AccessResult;
use Drupal\Core\Access\AccessResultInterface;
use Drupal\Core\Session\AccountInterface;

/**
 * Who may open a signature's or a task's pages: the person who made it (with "keep signatures and tasks"), or
 * anyone with "administer signatures and tasks".
 */
class SignatureTaskAccess {

  public static function signature(AccountInterface $account, string $signature_id): AccessResultInterface {
    return self::check($account, fn (BibleManager $manager) => $manager->getSignature((int) $signature_id));
  }

  public static function task(AccountInterface $account, string $task_id): AccessResultInterface {
    return self::check($account, fn (BibleManager $manager) => $manager->getTask((int) $task_id));
  }

  private static function check(AccountInterface $account, callable $load): AccessResultInterface {
    if ($account->hasPermission('administer signatures and tasks')) {
      return AccessResult::allowed()->cachePerPermissions();
    }
    if (!$account->hasPermission('keep signatures and tasks')) {
      return AccessResult::forbidden()->cachePerPermissions();
    }
    try {
      // getSignature and getTask refuse one that is not this user's.
      $load(\Drupal::service('bible_admin.manager'));
      $allowed = TRUE;
    }
    catch (BibleManagerException) {
      $allowed = FALSE;
    }
    return AccessResult::allowedIf($allowed)->setCacheMaxAge(0);
  }

}
