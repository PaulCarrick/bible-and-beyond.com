<?php

// Run once by the web container's first start (drush php:script): gives the first administrator (user 1)
// the password in STACK_ADMIN_PASSWORD, read from the environment so it never appears in a command line.

use Drupal\user\Entity\User;

$password = (string) getenv('STACK_ADMIN_PASSWORD');
if ($password === '') {
  throw new \RuntimeException('No password given.');
}
$account = User::load(1);
$account->setPassword($password);
$account->save();
echo "Set the administrator's password.\n";
