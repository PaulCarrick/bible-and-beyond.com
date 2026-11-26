<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;

/**
 * "Add one of your verse cards" (added 2026-11-26 at the owner's request) on a group's Send a message, a scheduled
 * message and Email a member: the saved verse cards (My cards on the site; saved_cards.py) of the site account of the
 * person sending (linked to their admin account on Site users, else the one with their email address), newest first,
 * as a table of radios with each card's picture, "No card" to start. Its value is the form's "saved_card".
 */
final class SavedCardChoice {

  /**
   * The choice, in a details element. $kept: the card already on a scheduled message being changed (kept even when it
   * belongs to whoever set it up rather than to the person changing it).
   */
  public static function element(BibleManager $manager, FormStateInterface $form_state, ?int $kept = NULL): array {
    $chosen = (string) ($form_state->getValue('saved_card') ?? ($kept ? (string) $kept : 'none'));
    $element = [
      '#type' => 'details',
      '#title' => t('Add one of your verse cards'),
      '#open' => ctype_digit($chosen),
    ];
    try {
      $found = $form_state->get('saved_cards') ?? $manager->adminSavedCards();
      $form_state->set('saved_cards', $found);
    }
    catch (BibleManagerException $exception) {
      $element['problem'] = ['#markup' => t('Your verse cards could not be read: @problem', ['@problem' => $exception->getMessage()])];
      return $element;
    }
    $account = $found['account'] ?? NULL;
    $options = ['none' => ['picture' => '', 'card' => t('No card')]];
    if ($account === NULL) {
      $element['none'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => t('Your admin account is not linked to an account on the site, so it has no verse cards. Give your site account the same email address as this admin account, or choose this admin account under <em>Drupal administrator account</em> on your Site users entry.'),
      ];
    }
    else {
      $name = $account['name'] . ($account['email'] ? ' (' . $account['email'] . ')' : '');
      $edit = Url::fromRoute('bible_admin.site_user_edit', ['user_id' => $account['id']]);
      $element['account'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        'label' => ['#markup' => t('Cards on My cards of your site account:') . ' '],
        'name' => $edit->access() ? ['#type' => 'link', '#title' => $name, '#url' => $edit] : ['#plain_text' => $name],
      ];
      if (empty($found['cards'])) {
        $element['empty'] = [
          '#type' => 'html_tag',
          '#tag' => 'p',
          '#value' => t('You have no cards yet. Make one on the site (Verse of the day > Make your own card); every card you download or send there is kept on My cards.'),
        ];
      }
      foreach ($found['cards'] ?? [] as $card) {
        $options[(string) $card['id']] = [
          'picture' => [
            'data' => [
              '#type' => 'html_tag',
              '#tag' => 'img',
              '#attributes' => [
                'src' => $card['thumbnail'],
                'alt' => $card['words'] . ' ' . $card['caption'],
                'width' => 96,
                'style' => 'height:auto;display:block;border-radius:6px;',
              ],
            ],
          ],
          'card' => $card['caption'] . ' · ' . date('M j, Y', strtotime((string) $card['created_at'])),
        ];
      }
    }
    if ($kept && !isset($options[(string) $kept])) {
      $options[(string) $kept] = ['picture' => '', 'card' => t('The card chosen when this was set up (not one of yours)')];
    }
    if (count($options) === 1) {
      return $element;
    }
    $element['saved_card'] = [
      '#type' => 'tableselect',
      '#header' => ['picture' => t('Card'), 'card' => t('Verse')],
      '#options' => $options,
      '#multiple' => FALSE,
      '#default_value' => isset($options[$chosen]) ? $chosen : 'none',
      '#parents' => ['saved_card'],
    ];
    $element['hint'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => t('The card is shown in the email and attached to it as a picture to save (and sent as a picture text to members who get texts, for a group message).'),
    ];
    return $element;
  }

  /**
   * The card chosen, or NULL for none.
   */
  public static function value(FormStateInterface $form_state): ?int {
    $value = (string) ($form_state->getValue('saved_card') ?? 'none');
    return ctype_digit($value) ? (int) $value : NULL;
  }

}
