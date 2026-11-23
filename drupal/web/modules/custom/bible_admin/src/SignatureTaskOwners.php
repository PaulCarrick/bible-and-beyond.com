<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\Session\AccountInterface;

/**
 * Who may own a signature or a task (added 2026-11-23, the owner's request, after a signature made while logged in
 * as "admin" did not show on PaulCarrick's tasks): the active Drupal users with "keep signatures and tasks" or
 * "administer signatures and tasks". An administrator chooses among them in the Owner select of the Signature and
 * Task forms, as the Leader select does for groups.
 */
class SignatureTaskOwners {

  /**
   * The possible owners by name ("Name (address)"), and the current owner in any case.
   */
  public static function options(int $currentOwner): array {
    $options = [];
    foreach (\Drupal::entityTypeManager()->getStorage('user')->loadByProperties(['status' => 1]) as $user) {
      if ($user->id() && ((int) $user->id() === $currentOwner || self::mayOwn($user))) {
        $options[(int) $user->id()] = $user->getDisplayName() . ($user->getEmail() ? ' (' . $user->getEmail() . ')' : '');
      }
    }
    natcasesort($options);
    return $options;
  }

  public static function mayOwn(AccountInterface $account): bool {
    return $account->hasPermission('keep signatures and tasks') || $account->hasPermission('administer signatures and tasks');
  }

  /**
   * The Drupal account of a chosen owner, or NULL when there is none.
   */
  public static function load(int $uid): ?AccountInterface {
    $user = \Drupal::entityTypeManager()->getStorage('user')->load($uid);
    return $user instanceof AccountInterface ? $user : NULL;
  }

}
