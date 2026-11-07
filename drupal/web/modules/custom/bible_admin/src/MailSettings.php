<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * The email server settings and the contact form's addresses.
 *
 * They are kept in Drupal's own configuration, never in the Bible search database that the public
 * site reads, because they include a password. Nothing sends email with them yet: they are stored
 * here so that a contact form can use them when there is one.
 *
 * Until they are first saved, the values below are used. They are the settings of the owner's other
 * site (paul-carrick.com), as a starting point.
 */
final class MailSettings {

  public const CONFIG_NAME = 'bible_admin.mail';

  /**
   * How the server wants the user to sign in.
   */
  public const AUTHENTICATIONS = [
    'login' => 'login',
    'plain' => 'plain',
    'cram-md5' => 'cram-md5',
    'none' => 'none (no sign-in)',
  ];

  // What a new site starts with, before the Site settings screen is saved (the containers fill these from
  // their settings file). Nothing site-specific: the live site has its own values saved.
  public const DEFAULTS = [
    'smtp_host' => '',
    'smtp_port' => 587,
    'smtp_username' => '',
    'smtp_password' => '',
    'smtp_authentication' => 'login',
    'default_domain' => '',
    'from_address' => '',
    'to_address' => '',
    'subject' => 'Contact request from the website',
  ];

  /**
   * The saved settings, with the defaults for anything not saved yet.
   */
  public static function load(ConfigFactoryInterface $configFactory): array {
    $stored = $configFactory->get(self::CONFIG_NAME)->getRawData();
    return array_merge(self::DEFAULTS, array_intersect_key($stored, self::DEFAULTS));
  }

  /**
   * Saves the settings. The password is left as it was unless a new one is given or it is to be removed.
   *
   * @param array $values
   *   Every key of DEFAULTS except smtp_password, which is optional.
   * @param string|null $newPassword
   *   A new password, or NULL to keep the saved one.
   * @param bool $removePassword
   *   TRUE to delete the saved password.
   */
  public static function save(ConfigFactoryInterface $configFactory, array $values, ?string $newPassword, bool $removePassword): void {
    $config = $configFactory->getEditable(self::CONFIG_NAME);
    $current = self::load($configFactory);
    $password = $current['smtp_password'];
    if ($removePassword) {
      $password = '';
    }
    elseif ($newPassword !== NULL && $newPassword !== '') {
      $password = $newPassword;
    }
    $data = array_intersect_key($values, self::DEFAULTS);
    $data['smtp_port'] = (int) $data['smtp_port'];
    $data['smtp_password'] = $password;
    $config->setData($data)->save();
  }

}
