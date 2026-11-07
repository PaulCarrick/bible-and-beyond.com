<?php

// Run once by the web container's first start (drush php:script): saves the email server settings given
// in its settings file (docker/.env). Later changes are made on the Site settings screen.

use Drupal\bible_admin\MailSettings;

$values = [
  'smtp_host' => (string) getenv('SMTP_HOST'),
  'smtp_port' => (int) (getenv('SMTP_PORT') ?: 587),
  'smtp_username' => (string) getenv('SMTP_USERNAME'),
  'smtp_authentication' => getenv('SMTP_AUTHENTICATION') ?: 'login',
  'default_domain' => (string) getenv('SMTP_DEFAULT_DOMAIN'),
  'from_address' => getenv('MAIL_FROM') ?: (string) getenv('ADMIN_EMAIL'),
  'to_address' => getenv('CONTACT_EMAIL_TO') ?: (string) getenv('ADMIN_EMAIL'),
  'subject' => getenv('CONTACT_SUBJECT') ?: 'Contact request from the website',
];
if (!array_key_exists($values['smtp_authentication'], MailSettings::AUTHENTICATIONS)) {
  $values['smtp_authentication'] = 'login';
}
MailSettings::save(\Drupal::configFactory(), $values, getenv('SMTP_PASSWORD') ?: NULL, FALSE);
echo "Saved the email server settings (" . $values['smtp_host'] . ").\n";
