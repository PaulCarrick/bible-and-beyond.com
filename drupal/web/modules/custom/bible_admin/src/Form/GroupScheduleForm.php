<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Core\Datetime\TimeZoneFormHelper;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds a scheduled message to a group, or changes one (group_schedules.py; the owner's request, 2026-11-16):
 * what to send (a message, a random verse card, or the leader's words on a random picture) and when (once on a
 * date, every week on a weekday, every month on a day, or every month on the first to last of a weekday), at a
 * time in a time zone. The fields for each choice show only when it is chosen (#states).
 */
class GroupScheduleForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_group_schedule';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', ?string $schedule_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $group = $this->manager->getGroup((int) $group_id);
      $schedule = $schedule_id === NULL ? NULL : $this->manager->getGroupSchedule((int) $group_id, (int) $schedule_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    $form_state->set('group_id', (int) $group['id']);
    if ($schedule !== NULL) {
      $form_state->set('schedule_id', (int) $schedule['id']);
    }
    $weekdays = [
      0 => $this->t('Monday'), 1 => $this->t('Tuesday'), 2 => $this->t('Wednesday'), 3 => $this->t('Thursday'),
      4 => $this->t('Friday'), 5 => $this->t('Saturday'), 6 => $this->t('Sunday'),
    ];
    $when = fn (array $repeats) => ['visible' => [':input[name="repeat"]' => array_map(fn ($repeat) => ['value' => $repeat], $repeats)]];
    $what = fn (array $kinds) => ['visible' => [':input[name="kind"]' => array_map(fn ($kind) => ['value' => $kind], $kinds)]];

    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('For “@group”. It goes to every member who has not stopped the group\'s messages, by email (and by text to those who chose texts), within five minutes of the time chosen.', ['@group' => $group['name']]),
    ];
    $form['kind'] = [
      '#type' => 'radios',
      '#title' => $this->t('What to send'),
      '#options' => [
        'message' => $this->t('A message (your words, no picture)'),
        'verse' => $this->t('A verse card (a new random verse on a picture each time)'),
        'picture' => $this->t('A picture message (your words on a new random picture each time)'),
      ],
      '#default_value' => $schedule['kind'] ?? 'message',
      '#required' => TRUE,
    ];
    $form['subject'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Subject'),
      '#maxlength' => 200,
      '#default_value' => $schedule['subject'] ?? '',
      '#states' => $what(['message', 'picture']),
    ];
    // A message is written in the editor (GroupEditor; 2026-11-17): the email keeps its formatting, texts get the
    // words. A picture's words stay plain: they are written onto the picture.
    $isMessage = ($schedule['kind'] ?? 'message') === 'message';
    $form['message_box'] = [
      '#type' => 'container',
      '#states' => $what(['message']),
      'message' => GroupEditor::field((string) $this->t('Message'), $isMessage ? (string) (($schedule['html'] ?? '') ?: ($schedule['text'] ?? '')) : '', 8, FALSE),
    ];
    $form['text'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Words for the picture'),
      '#rows' => 3,
      '#maxlength' => 400,
      '#default_value' => $isMessage ? '' : ($schedule['text'] ?? ''),
      '#description' => $this->t('Up to 400 characters: the fewer the words, the larger they are written.'),
      '#states' => $what(['picture']),
    ];

    $form['when'] = ['#type' => 'fieldset', '#title' => $this->t('When')];
    $form['when']['repeat'] = [
      '#type' => 'select',
      '#title' => $this->t('Repeat'),
      '#options' => [
        'once' => $this->t('Once, on a date'),
        'weekly' => $this->t('Every week'),
        'monthly_day' => $this->t('Every month, on a day of the month (such as the 15th)'),
        'monthly_weekday' => $this->t('Every month, on a weekday (such as the first Monday)'),
      ],
      '#default_value' => $schedule['repeat'] ?? 'monthly_weekday',
      '#required' => TRUE,
    ];
    $form['when']['on_date'] = [
      '#type' => 'date',
      '#title' => $this->t('Date'),
      '#default_value' => $schedule['on_date'] ?? '',
      '#states' => $when(['once']),
    ];
    $form['when']['week_of_month'] = [
      '#type' => 'select',
      '#title' => $this->t('Which'),
      '#options' => [1 => $this->t('First'), 2 => $this->t('Second'), 3 => $this->t('Third'), 4 => $this->t('Fourth'), 5 => $this->t('Last')],
      '#default_value' => $schedule['week_of_month'] ?? 1,
      '#states' => $when(['monthly_weekday']),
    ];
    $form['when']['weekday'] = [
      '#type' => 'select',
      '#title' => $this->t('Day of the week'),
      '#options' => $weekdays,
      '#default_value' => $schedule['weekday'] ?? 0,
      '#states' => $when(['weekly', 'monthly_weekday']),
    ];
    $form['when']['day_of_month'] = [
      '#type' => 'select',
      '#title' => $this->t('Day of the month'),
      '#options' => array_combine(range(1, 31), range(1, 31)),
      '#default_value' => $schedule['day_of_month'] ?? 1,
      '#description' => $this->t('29, 30 or 31 means the last day in a month that is shorter.'),
      '#states' => $when(['monthly_day']),
    ];
    $form['when']['send_time'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Time'),
      '#attributes' => ['type' => 'time'],
      '#size' => 8,
      '#default_value' => $schedule['send_time'] ?? '09:00',
      '#required' => TRUE,
    ];
    $form['when']['timezone'] = [
      '#type' => 'select',
      '#title' => $this->t('Time zone'),
      '#options' => TimeZoneFormHelper::getOptionsListByRegion(),
      '#default_value' => $schedule['timezone'] ?? ($this->currentUser()->getTimeZone() ?: $this->config('system.date')->get('timezone.default')),
      '#required' => TRUE,
    ];

    // The signature at the end of its emails (2026-11-19, the owner's request: "Each schedule can have a different
    // signature"): one of the group leader's signatures, or none.
    $signatures = [];
    try {
      foreach ($this->manager->listLeaderSignatures($group) as $signature) {
        $signatures[(int) $signature['id']] = $signature['name'];
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $mine = (int) $group['owner_uid'] === (int) $this->currentUser()->id();
    $form['signature_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Signature'),
      '#options' => ['' => $this->t('- No signature -')] + $signatures,
      '#default_value' => isset($schedule['signature_id'], $signatures[(int) $schedule['signature_id']]) ? (int) $schedule['signature_id'] : '',
      '#description' => $signatures
        ? $this->t('Added after the words of every email this sends, before the stop links.')
        : ($mine
          ? $this->t('You have no signatures yet. Add one on the <a href=":url">Signatures</a> page, then choose it here.', [':url' => Url::fromRoute('bible_admin.signatures')->toString()])
          : $this->t('The group leader has no signatures yet.')),
    ];

    // "Add the “Sent by …” line" (2026-11-23, the owner's request): ticked to start; untick it for a message that
    // should end with your own words (and signature).
    $form['show_sent_by'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Add the “Sent by …” line at the foot'),
      '#default_value' => (bool) ($schedule['show_sent_by'] ?? TRUE),
      '#description' => $this->t('Such as “Sent by the leader to the group through the site.” Untick to leave it out of every email this sends. Each member’s stop links stay either way.'),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $schedule === NULL ? $this->t('Schedule it') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $form_state->get('group_id');
    $scheduleId = $form_state->get('schedule_id');
    $details = [];
    foreach (['kind', 'subject', 'repeat', 'on_date', 'day_of_month', 'weekday', 'week_of_month', 'send_time', 'timezone', 'signature_id'] as $name) {
      $details[$name] = (string) $form_state->getValue($name);
    }
    $details['show_sent_by'] = (bool) $form_state->getValue('show_sent_by');
    if ($details['kind'] === 'message') {
      $details += GroupEditor::value($form_state->getValue('message'));
    }
    else {
      $details['text'] = (string) $form_state->getValue('text');
    }
    try {
      $schedule = $scheduleId === NULL
        ? $this->manager->addGroupSchedule($groupId, $details)
        : $this->manager->updateGroupSchedule($groupId, (int) $scheduleId, $details);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('@when. The next one goes on @next.', ['@when' => $schedule['description'], '@next' => $schedule['next_run_local']]));
    $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
  }

}
