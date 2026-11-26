<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Sends to every member of a group who has not stopped the group's messages (groups.py):
 * - message: a subject and words, by email and text as each member chose; with, if chosen, one of the sender's own
 *   saved verse cards (My cards on the site; 2026-11-26), shown in the email, attached to it and sent as a picture
 *   text;
 * - verse: a random well-known verse card, shown first ("Pick another verse" for another), sent as shown;
 * - picture: the leader's words over a random verse a day picture, made and shown first, sent as shown.
 */
class GroupSendForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_group_send';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', string $kind = 'message'): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $group = $this->manager->getGroup((int) $group_id);
      // The verse card is chosen as soon as the page opens.
      if ($kind === 'verse' && !$form_state->get('preview')) {
        $form_state->set('preview', $this->manager->previewGroupVerse());
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    $form_state->set('group_id', (int) $group['id']);
    $form_state->set('kind', $kind);
    $active = count(array_filter($group['members'], fn ($member) => !$member['stopped']));
    $preview = $form_state->get('preview');

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => match ($kind) {
        'verse' => $this->t('A Bible verse chosen at random from about 1,500 of the best-known, written over one of the verse a day pictures. It goes in the email (the verse a link to it on the site) and as a picture text to those who get texts. Not the one you want? Pick another.'),
        'picture' => $this->t('Your own words written over one of the verse a day pictures, chosen at random. Make the picture to see it before sending; make another for a different picture.'),
        default => $this->t('By email, and by text to members who chose texts. Texts are short, so a long message is cut there (the email has it all). You can add one of your own verse cards (made on the site with Make your own card) below.'),
      },
    ];

    if ($kind !== 'verse') {
      $form['subject'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Subject'),
        '#maxlength' => 200,
        '#required' => TRUE,
        '#default_value' => $form_state->getValue('subject', ''),
      ];
      if ($kind === 'picture') {
        // Plain words: they are written onto the picture, where formatting cannot show.
        $form['text'] = [
          '#type' => 'textarea',
          '#title' => $this->t('Words for the picture'),
          '#rows' => 3,
          '#maxlength' => 400,
          '#required' => TRUE,
          '#default_value' => $form_state->getValue('text', ''),
          '#description' => $this->t('Up to 400 characters; the fewer the words, the larger they are written.'),
        ];
      }
      else {
        // The editor (GroupEditor; 2026-11-17): the email keeps its formatting, texts get the words.
        $typed = $form_state->getValue('text', '');
        $form['text'] = GroupEditor::field((string) $this->t('Message'), is_array($typed) ? (string) ($typed['value'] ?? '') : (string) $typed, 8, TRUE);
      }
    }

    if ($kind === 'message') {
      $form['saved_card_box'] = $this->savedCardChoice($form_state);
    }

    if ($preview) {
      $form['preview'] = [
        '#type' => 'html_tag',
        '#tag' => 'img',
        '#attributes' => [
          'src' => $preview['image'],
          'alt' => $preview['words'] . (isset($preview['caption']) ? ' ' . $preview['caption'] : ''),
          'width' => 360,
          'style' => 'height:auto;display:block;border-radius:8px;margin:1em 0;',
        ],
      ];
    }

    // "Add the “Sent by …” line" (2026-11-23, the owner's request): ticked to start; untick it for a message that
    // should end with your own words (and signature).
    $form['show_sent_by'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Add the “Sent by …” line at the foot'),
      '#default_value' => TRUE,
      '#description' => $this->t('Such as “Sent by @name to the group “@group” through the site.” Untick to leave it out. Each member’s stop links stay either way.', ['@name' => $group['owner_name'] ?: $this->t('the leader'), '@group' => $group['name']]),
    ];

    $form['actions'] = ['#type' => 'actions'];
    if ($kind === 'verse') {
      $form['actions']['another'] = [
        '#type' => 'submit',
        '#value' => $this->t('Pick another verse'),
        '#submit' => ['::makePreview'],
        '#limit_validation_errors' => [],
      ];
    }
    if ($kind === 'picture') {
      $form['actions']['make'] = [
        '#type' => 'submit',
        '#value' => $preview ? $this->t('Make another picture') : $this->t('Make the picture'),
        '#submit' => ['::makePreview'],
        '#limit_validation_errors' => [['text'], ['subject']],
      ];
    }
    if ($kind !== 'picture' || $preview) {
      $form['actions']['submit'] = [
        '#type' => 'submit',
        '#button_type' => 'primary',
        '#value' => $this->formatPlural($active, 'Send to the 1 member', 'Send to the @count members'),
        '#disabled' => $active === 0,
      ];
    }
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  /**
   * "Add one of your verse cards": the saved cards of the site account of the person sending (linked to their
   * admin account on Site users, else the one with their email address), newest first, as a table of radios with
   * each card's picture; "No card" to start.
   */
  protected function savedCardChoice(FormStateInterface $form_state): array {
    $element = [
      '#type' => 'details',
      '#title' => $this->t('Add one of your verse cards'),
      '#open' => ctype_digit((string) $form_state->getValue('saved_card', '')),
    ];
    try {
      $found = $form_state->get('saved_cards') ?? $this->manager->adminSavedCards();
      $form_state->set('saved_cards', $found);
    }
    catch (BibleManagerException $exception) {
      $element['problem'] = ['#markup' => $this->t('Your verse cards could not be read: @problem', ['@problem' => $exception->getMessage()])];
      return $element;
    }
    $account = $found['account'] ?? NULL;
    if ($account === NULL) {
      $element['#open'] = FALSE;
      $element['none'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Your admin account is not linked to an account on the site, so it has no verse cards. Give your site account the same email address as this admin account, or choose this admin account under <em>Drupal administrator account</em> on your Site users entry.'),
      ];
      return $element;
    }
    $name = $account['name'] . ($account['email'] ? ' (' . $account['email'] . ')' : '');
    $edit = Url::fromRoute('bible_admin.site_user_edit', ['user_id' => $account['id']]);
    $element['account'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      'label' => ['#markup' => $this->t('Cards on My cards of your site account:') . ' '],
      'name' => $edit->access() ? ['#type' => 'link', '#title' => $name, '#url' => $edit] : ['#plain_text' => $name],
    ];
    if (empty($found['cards'])) {
      $element['empty'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('You have no cards yet. Make one on the site (Verse of the day > Make your own card); every card you download or send there is kept on My cards.'),
      ];
      return $element;
    }
    $options = ['none' => ['picture' => '', 'card' => $this->t('No card')]];
    foreach ($found['cards'] as $card) {
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
    $element['saved_card'] = [
      '#type' => 'tableselect',
      '#header' => ['picture' => $this->t('Card'), 'card' => $this->t('Verse')],
      '#options' => $options,
      '#multiple' => FALSE,
      '#default_value' => (string) $form_state->getValue('saved_card', 'none'),
      '#parents' => ['saved_card'],
    ];
    $element['hint'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('The card is shown in the email, attached to it as a picture to save, and sent as a picture text to members who get texts.'),
    ];
    return $element;
  }

  /**
   * Another verse card, or the picture made (again) from the words typed.
   */
  public function makePreview(array &$form, FormStateInterface $form_state): void {
    try {
      $form_state->set('preview', $form_state->get('kind') === 'verse'
        ? $this->manager->previewGroupVerse()
        : $this->manager->previewGroupPicture((string) $form_state->getValue('text')));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRebuild();
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $trigger = $form_state->getTriggeringElement();
    if (($trigger['#submit'] ?? NULL) !== NULL) {
      return;
    }
    $preview = $form_state->get('preview');
    if ($form_state->get('kind') === 'picture' && (!$preview || trim((string) $preview['words']) !== trim((string) $form_state->getValue('text')))) {
      $form_state->setErrorByName('text', $this->t('The words have changed since the picture was made: make the picture again to see it before sending.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $form_state->get('group_id');
    $kind = (string) $form_state->get('kind');
    $preview = $form_state->get('preview') ?? [];
    $details = match ($kind) {
      'verse' => ['card' => $preview['card'] ?? '', 'verse' => $preview['verse'] ?? []],
      'picture' => ['subject' => (string) $form_state->getValue('subject'), 'text' => (string) $form_state->getValue('text'), 'card' => $preview['card'] ?? ''],
      default => ['subject' => (string) $form_state->getValue('subject')] + GroupEditor::value($form_state->getValue('text')),
    };
    $savedCard = (string) ($form_state->getValue('saved_card') ?? 'none');
    if ($kind === 'message' && ctype_digit($savedCard)) {
      $details['saved_card'] = (int) $savedCard;
    }
    $details['show_sent_by'] = (bool) $form_state->getValue('show_sent_by');
    try {
      $counts = $this->manager->sendToGroup($groupId, $kind, $details);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('Sent: @emailed emailed, @texted texted.', ['@emailed' => $counts['emailed'], '@texted' => $counts['texted']]));
    if ($counts['skipped']) {
      $this->messenger()->addWarning($this->formatPlural($counts['skipped'],
        'One member was skipped: they have not confirmed their email address on the site yet, or they stopped the group\'s messages.',
        '@count members were skipped: they have not confirmed their email address on the site yet, or they stopped the group\'s messages.'));
    }
    if ($counts['failed']) {
      $this->messenger()->addError($this->formatPlural($counts['failed'],
        'One could not be sent (the details are in the log). Nothing is tried again by itself.',
        '@count could not be sent (the details are in the log). Nothing is tried again by itself.'));
    }
    $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
  }

}
