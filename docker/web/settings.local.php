<?php

// Drupal's settings in the web container (docker/web). Everything comes from the environment
// (docker/.env, passed in by docker/compose.yml), so the image holds no password.

$databases['default']['default'] = [
  'driver' => 'mysql',
  'database' => 'bibleandbeyond_drupal',
  'username' => getenv('DRUPAL_DATABASE_USER') ?: 'drupal',
  'password' => getenv('DRUPAL_DATABASE_PASSWORD') ?: '',
  'host' => getenv('DRUPAL_DATABASE_HOST') ?: 'database',
  'port' => 3306,
  'prefix' => '',
  'collation' => 'utf8mb4_general_ci',
  'namespace' => 'Drupal\\mysql\\Driver\\Database\\mysql',
  'autoload' => 'core/modules/mysql/src/Driver/Database/mysql/',
  // Drupal recommends READ COMMITTED; MariaDB defaults to REPEATABLE READ.
  'init_commands' => [
    'isolation_level' => 'SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
  ],
];

// DRUPAL_HASH_SALT if given, else one made on the first start and kept in the private volume.
$settings['hash_salt'] = getenv('DRUPAL_HASH_SALT') ?: trim((string) @file_get_contents('/app/drupal-private/hash_salt'));

// localhost, plus any patterns in DRUPAL_TRUSTED_HOSTS (comma-separated regular expressions).
$settings['trusted_host_patterns'] = array_merge(
  ['^localhost$', '^127\.0\.0\.1$'],
  array_filter(array_map('trim', explode(',', (string) getenv('DRUPAL_TRUSTED_HOSTS')))),
);

$settings['file_private_path'] = '/app/drupal-private';
$settings['config_sync_directory'] = '/app/drupal-config';
