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
 * Message a day (added 2026-11-23 at the owner's request): a message to the people scheduled on one date. The Date
 * list holds the dates from today on with something scheduled; the people of that date are ticked boxes (untick
 * anyone to leave out); then a subject, the message in the editor and a signature. Each person gets it the way they
 * chose on My account (day_messages.py).
 */
class DayMessageForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_day_message';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $dates = $this->manager->dayMessageDates();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $form;
    }
    if (!$dates) {
      $form['none'] = [
        '#markup' => '<p>' . $this->t('Nothing is scheduled from today on. Schedule tasks first, then message the people of a day.') . '</p>',
      ];
      $form['back'] = ['#type' => 'link', '#title' => $this->t('Back to the scheduled tasks'), '#url' => Url::fromRoute('bible_admin.scheduled_tasks')];
      return $form;
    }
    $dateOptions = [];
    foreach ($dates as $day) {
      $dateOptions[$day['value']] = $this->formatPlural((int) $day['people'], '@day (1 person)', '@day (@count people)', ['@day' => $day['label']]);
    }
    $onDate = (string) ($form_state->getValue('on_date') ?? array_key_first($dateOptions));
    if (!isset($dateOptions[$onDate])) {
      $onDate = (string) array_key_first($dateOptions);
    }

    $form['on_date'] = [
      '#type' => 'select',
      '#title' => $this->t('Date'),
      '#options' => $dateOptions,
      '#default_value' => $onDate,
      '#ajax' => ['callback' => '::refreshPeople', 'wrapper' => 'day-message-people', 'event' => 'change'],
    ];
    $form['people_box'] = ['#type' => 'container', '#attributes' => ['id' => 'day-message-people']];
    try {
      $people = $this->manager->dayMessagePeople($onDate);
    }
    catch (BibleManagerException $exception) {
      $form['people_box']['message'] = ['#markup' => '<p>' . $this->t('@message', ['@message' => $exception->getMessage()]) . '</p>'];
      $people = [];
    }
    $peopleOptions = [];
    foreach ($people as $person) {
      $peopleOptions[(int) $person['id']] = $this->t('@person: @tasks', ['@person' => $person['label'], '@tasks' => implode(', ', $person['tasks'])]);
    }
    // Named after the date, so another date's people all start ticked (a box keeps what was typed for its name).
    $peopleKey = 'people_' . str_replace('-', '', $onDate);
    $form_state->set('people_key', $peopleKey);
    $form['people_box'][$peopleKey] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('Send it to'),
      '#options' => $peopleOptions,
      '#default_value' => array_keys($peopleOptions),
      '#description' => $this->t('Everyone scheduled that day, with their tasks. Untick anyone to leave out. Each gets it the way they chose on their My account page: by email, text or both.'),
    ];

    $form['subject'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Subject'),
      '#maxlength' => 200,
      '#default_value' => $this->t('About @day', ['@day' => preg_replace('/,\s*\d{4}$/', '', $dates[0]['label'])]),
      '#description' => $this->t('A text message starts with it.'),
    ];
    $form['message'] = GroupEditor::field(
      (string) $this->t('Message'),
      '',
      8,
      FALSE,
      (string) $this->t('[FIRST_NAME], [LAST_NAME] and [FULL_NAME] are replaced with each person’s name (“friend” when the account has no name). Replies come to your email address.'),
    );
    $signatures = [];
    try {
      foreach ($this->manager->listLeaderSignatures(['owner_uid' => (int) $this->currentUser()->id()]) as $signature) {
        $signatures[(int) $signature['id']] = $signature['name'];
      }
    }
    catch (BibleManagerException) {
    }
    $form['signature_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Signature'),
      '#options' => ['' => $this->t('- No signature -')] + $signatures,
      '#description' => $signatures
        ? $this->t('Added at the foot of the emails (not texts).')
        : $this->t('You have no signatures yet. Add one on the <a href=":url">Signatures</a> page, then choose it here.', [':url' => Url::fromRoute('bible_admin.signatures')->toString()]),
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $this->t('Send'), '#button_type' => 'primary'];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.scheduled_tasks'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function refreshPeople(array $form, FormStateInterface $form_state): array {
    return $form['people_box'];
  }

  /**
   * The people still ticked.
   */
  private function chosen(FormStateInterface $form_state): array {
    $key = (string) $form_state->get('people_key');
    return array_values(array_map('intval', array_keys(array_filter((array) $form_state->getValue($key, [])))));
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $trigger = $form_state->getTriggeringElement();
    if (($trigger['#type'] ?? '') !== 'submit') {
      return;
    }
    if (!$this->chosen($form_state)) {
      $form_state->setErrorByName((string) $form_state->get('people_key'), $this->t('Tick at least one person to send it to.'));
    }
    if (trim((string) $form_state->getValue('subject')) === '') {
      $form_state->setErrorByName('subject', $this->t('Give the message a subject.'));
    }
    $message = GroupEditor::value($form_state->getValue('message'));
    if (trim(strip_tags((string) ($message['html'] ?? $message['text'] ?? ''))) === '') {
      $form_state->setErrorByName('message', $this->t('Write the message.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $onDate = (string) $form_state->getValue('on_date');
    try {
      $result = $this->manager->sendDayMessage(
        $onDate,
        $this->chosen($form_state),
        (string) $form_state->getValue('subject'),
        GroupEditor::value($form_state->getValue('message')),
        (string) $form_state->getValue('signature_id'),
      );
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    if ($result['sent']) {
      $this->messenger()->addStatus($this->formatPlural(count($result['sent']), 'Sent to 1 person: @people.', 'Sent to @count people: @people.', [
        '@people' => implode('; ', array_map(fn ($sent) => $sent['label'] . ' (' . $sent['how'] . ')', $result['sent'])),
      ]));
    }
    foreach ($result['not_sent'] as $missed) {
      $this->messenger()->addWarning($this->t('Not sent to @person: @why', ['@person' => $missed['label'], '@why' => $missed['why']]));
    }
    $form_state->setRedirect('bible_admin.scheduled_tasks');
  }

}
