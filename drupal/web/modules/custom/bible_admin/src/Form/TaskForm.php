<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\bible_admin\SignatureTaskOwners;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds a task (belonging to the user adding it) or changes one: a name, a formatted description, how often it
 * comes round (weekly every few weeks on weekdays, monthly on a day, or monthly on the first ... last of weekdays,
 * every few months or once a year, from a start date) and the words of
 * its first and second notifications (formatted, in the group emails' editor), each with how many days before a
 * scheduled date it is emailed to the site user (scheduled_tasks.send_due, at 8:00 AM in the owner's time zone).
 */
class TaskForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_task';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $task_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $task = NULL;
    if ($task_id !== NULL) {
      try {
        $task = $this->manager->getTask((int) $task_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the tasks'), '#url' => Url::fromRoute('bible_admin.tasks')]];
      }
      $form_state->set('task_id', (int) $task['id']);
    }
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#default_value' => $task['name'] ?? '',
      '#maxlength' => 200,
      '#required' => TRUE,
    ];
    $form['description'] = GroupEditor::field((string) $this->t('Description'), (string) ($task['description_html'] ?? ''), 5, FALSE);

    // How often (the owner's request, 2026-11-19: "the first .. of the ...", "It's not just the month"): weekly every
    // few weeks on weekdays, monthly on a day, or monthly on the first ... last of weekdays, every few months or once
    // a year, from a start date (admin_tasks.py).
    $form['recurrence'] = [
      '#type' => 'fieldset',
      '#title' => $this->t('How often'),
    ];
    $repeat = $task['repeat'] ?? 'weekly';
    $every = (int) ($task['interval_count'] ?? 1);
    $form['recurrence']['repeat'] = [
      '#type' => 'radios',
      '#title' => $this->t('Comes round'),
      '#title_display' => 'invisible',
      '#options' => [
        'weekly' => $this->t('Weekly'),
        'monthly_day' => $this->t('Monthly, on a day of the month (such as the 15th)'),
        'monthly_weekday' => $this->t('Monthly, on a weekday (such as the first Sunday)'),
      ],
      '#default_value' => $repeat,
      '#required' => TRUE,
    ];
    $weekly = [':input[name="repeat"]' => ['value' => 'weekly']];
    $monthly = [':input[name="repeat"]' => [['value' => 'monthly_day'], ['value' => 'monthly_weekday']]];
    $onWeekdays = [':input[name="repeat"]' => [['value' => 'weekly'], ['value' => 'monthly_weekday']]];
    $byWeekday = [':input[name="repeat"]' => ['value' => 'monthly_weekday']];
    $byDay = [':input[name="repeat"]' => ['value' => 'monthly_day']];
    $weeksApart = [1 => $this->t('Every week')];
    foreach (range(2, 8) as $weeks) {
      $weeksApart[$weeks] = $this->t('Every @count weeks', ['@count' => $weeks]);
    }
    $form['recurrence']['weeks_apart'] = [
      '#type' => 'select',
      '#title' => $this->t('How many weeks apart'),
      '#options' => $weeksApart,
      '#default_value' => $repeat === 'weekly' ? $every : 1,
      '#states' => ['visible' => $weekly],
    ];
    $form['recurrence']['months_apart'] = [
      '#type' => 'select',
      '#title' => $this->t('How many months apart'),
      '#options' => [
        1 => $this->t('Every month'),
        2 => $this->t('Every 2 months'),
        3 => $this->t('Every 3 months (quarterly)'),
        4 => $this->t('Every 4 months'),
        6 => $this->t('Every 6 months'),
        12 => $this->t('Once a year'),
      ],
      '#default_value' => $repeat === 'weekly' ? 1 : $every,
      '#states' => ['visible' => $monthly],
    ];
    $form['recurrence']['weeks_of_month'] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('Which'),
      '#options' => [
        1 => $this->t('First'),
        2 => $this->t('Second'),
        3 => $this->t('Third'),
        4 => $this->t('Fourth'),
        5 => $this->t('Last'),
      ],
      '#default_value' => $task['weeks_of_month'] ?? [],
      '#description' => $this->t('One or more: the first and third Sunday, for example.'),
      '#states' => ['visible' => $byWeekday],
    ];
    // The keys are 1 (Monday) to 7 (Sunday): a checkbox whose key is 0 cannot be told from one left empty.
    $form['recurrence']['weekdays'] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('Day of the week'),
      '#options' => [
        1 => $this->t('Monday'),
        2 => $this->t('Tuesday'),
        3 => $this->t('Wednesday'),
        4 => $this->t('Thursday'),
        5 => $this->t('Friday'),
        6 => $this->t('Saturday'),
        7 => $this->t('Sunday'),
      ],
      '#default_value' => array_map(fn ($weekday) => (int) $weekday + 1, $task['weekdays'] ?? []),
      '#description' => $this->t('One or more.'),
      '#states' => ['visible' => $onWeekdays],
    ];
    $form['recurrence']['day_of_month'] = [
      '#type' => 'number',
      '#title' => $this->t('Day of the month'),
      '#min' => 1,
      '#max' => 31,
      '#default_value' => $task['day_of_month'] ?? NULL,
      '#description' => $this->t('1 to 31. The 29th, 30th and 31st mean the last day in shorter months.'),
      '#states' => ['visible' => $byDay, 'required' => $byDay],
    ];
    $form['recurrence']['first_date'] = [
      '#type' => 'date',
      '#title' => $this->t('Starting'),
      '#default_value' => $task['first_date'] ?? (new \DateTimeImmutable('now', new \DateTimeZone($this->currentUser()->getTimeZone() ?: 'UTC')))->format('Y-m-d'),
      '#required' => TRUE,
      '#description' => $this->t('No date comes before this one. Every few weeks or months counts from its week or month, and a task once a year comes in its month.'),
    ];

    foreach (['first' => $this->t('First notification'), 'second' => $this->t('Second notification')] as $which => $title) {
      $form[$which . '_notification'] = GroupEditor::field((string) $title, (string) ($task[$which . '_notification_html'] ?? ''), 4, FALSE, (string) $this->t('[FIRST_NAME], [LAST_NAME] and [FULL_NAME] are replaced with the site user’s name (“friend” when the account has no name).'));
      $form[$which . '_notice_days'] = [
        '#type' => 'number',
        '#title' => $this->t('Days before'),
        '#min' => 0,
        '#max' => 90,
        '#default_value' => $task[$which . '_notice_days'] ?? NULL,
        '#field_suffix' => $this->t('days before the scheduled date'),
        '#description' => $which === 'first'
          ? $this->t('The first notification is sent to the site user (by email, text or both, as they chose on My account) this many days before each date the task is scheduled for them, at 8:00 AM your time. Leave it empty to send none.')
          : $this->t('Fewer days than the first (1 for the day before, 0 for the day itself). Leave it empty to send none.'),
      ];
    }

    // An administrator chooses whose it is (2026-11-23): a signature or task is only ever used with its owner's.
    if ($this->currentUser()->hasPermission('administer signatures and tasks')) {
      $currentOwner = (int) ($task['owner_uid'] ?? $this->currentUser()->id());
      $form['owner_uid'] = [
        '#type' => 'select',
        '#title' => $this->t('Owner'),
        '#options' => SignatureTaskOwners::options($currentOwner),
        '#default_value' => $currentOwner,
        '#required' => TRUE,
        '#description' => $this->t('Whose task this is: its reminders go out in their name, replies go to their address, and they choose its signature. Moving it keeps its scheduled dates; a signature that is not the new owner’s is dropped.'),
      ];
    }

    // The signature at the foot of the reminder emails (2026-11-23, the owner's request): one of the task owner's
    // signatures, or none. Texts never carry it.
    $ownerUid = $task === NULL ? (int) $this->currentUser()->id() : (int) $task['owner_uid'];
    $signatures = [];
    try {
      foreach ($this->manager->listLeaderSignatures(['owner_uid' => $ownerUid]) as $signature) {
        $signatures[(int) $signature['id']] = $signature['name'];
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addWarning($exception->getMessage());
    }
    $form['signature_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Signature'),
      '#options' => ['' => $this->t('- No signature -')] + $signatures,
      '#default_value' => isset($task['signature_id'], $signatures[(int) $task['signature_id']]) ? (int) $task['signature_id'] : '',
      '#description' => $signatures
        ? $this->t('Added at the foot of the reminder emails (not texts).')
        : ($ownerUid === (int) $this->currentUser()->id()
          ? $this->t('You have no signatures yet. Add one on the <a href=":url">Signatures</a> page, then choose it here.', [':url' => Url::fromRoute('bible_admin.signatures')->toString()])
          : $this->t('The task’s owner has no signatures yet.')),
    ];

    // "Add the “Sent by …” line" (2026-11-23, the owner's request): ticked to start; untick it for a message that
    // should end with your own words (and signature).
    $form['show_sent_by'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Add the “Sent by …” line at the foot'),
      '#default_value' => (bool) ($task['show_sent_by'] ?? TRUE),
      '#description' => $this->t('Such as “A reminder of “Coffee” on Sunday, November 29, from Paul through the site.” Untick to leave it out of this task’s reminder emails.'),
    ];

    // The sign-up sheet (Scheduled tasks; 2026-11-27, the owner's request).
    $form['sheet'] = [
      '#type' => 'details',
      '#title' => $this->t('Sign-up sheet'),
      '#open' => TRUE,
    ];
    $form['sheet']['expected_occurrences'] = [
      '#type' => 'number',
      '#title' => $this->t('Expected occurrences'),
      '#min' => 1,
      '#max' => 20,
      '#step' => 1,
      '#required' => TRUE,
      '#default_value' => (int) ($task['expected_occurrences'] ?? 1),
      '#description' => $this->t('How many people the task needs on each of its dates (2 for “Baked Goods 1” and “Baked Goods 2”). A blank sign-up sheet has that many rows for it, numbered when more than one, and members cannot ask for a date that already has that many.'),
    ];
    $form['sheet']['sheet_order'] = [
      '#type' => 'number',
      '#title' => $this->t('Order on the sign-up sheet'),
      '#min' => 0,
      '#max' => 999,
      '#step' => 1,
      '#default_value' => (int) ($task['sheet_order'] ?? 0),
      '#description' => $this->t('Where the task comes within each date on the sheet: lowest first (1, 2, 3 …); tasks with the same number go by name.'),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $task === NULL ? $this->t('Add the task') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.tasks'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    // #states only shows the fields in the browser; the fields of the chosen repeat are checked here.
    $repeat = $form_state->getValue('repeat');
    if (in_array($repeat, ['weekly', 'monthly_weekday'], TRUE) && !$this->checked($form_state->getValue('weekdays'))) {
      $form_state->setErrorByName('weekdays', $this->t('Choose the day of the week.'));
    }
    if ($repeat === 'monthly_weekday' && !$this->checked($form_state->getValue('weeks_of_month'))) {
      $form_state->setErrorByName('weeks_of_month', $this->t('Choose which one in the month: the first, second, third, fourth or last.'));
    }
    if ($repeat === 'monthly_day' && (string) $form_state->getValue('day_of_month') === '') {
      $form_state->setErrorByName('day_of_month', $this->t('Choose a day of the month from 1 to 31.'));
    }
  }

  /**
   * The keys of the ticked boxes of a checkboxes element.
   */
  private function checked(mixed $value): array {
    return array_values(array_map('intval', array_keys(array_filter((array) $value))));
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $taskId = $form_state->get('task_id');
    $repeat = (string) $form_state->getValue('repeat');
    try {
      $task = $this->manager->saveTask($taskId === NULL ? NULL : (int) $taskId, [
        'name' => (string) $form_state->getValue('name'),
        'description' => GroupEditor::value($form_state->getValue('description')),
        'repeat' => $repeat,
        'interval_count' => (int) $form_state->getValue($repeat === 'weekly' ? 'weeks_apart' : 'months_apart'),
        // The boxes are 1 (Monday) to 7 (Sunday); the ML service counts 0 (Monday) to 6 (Sunday).
        'weekdays' => array_map(fn ($day) => $day - 1, $this->checked($form_state->getValue('weekdays'))),
        'weeks_of_month' => $this->checked($form_state->getValue('weeks_of_month')),
        'first_date' => (string) $form_state->getValue('first_date'),
        'day_of_month' => $repeat === 'monthly_day' ? (int) $form_state->getValue('day_of_month') : NULL,
        'first_notification' => GroupEditor::value($form_state->getValue('first_notification')),
        'second_notification' => GroupEditor::value($form_state->getValue('second_notification')),
        'first_notice_days' => $this->days($form_state->getValue('first_notice_days')),
        'second_notice_days' => $this->days($form_state->getValue('second_notice_days')),
        'signature_id' => (string) $form_state->getValue('signature_id'),
        'owner_uid' => $form_state->getValue('owner_uid') ? (int) $form_state->getValue('owner_uid') : NULL,
        'show_sent_by' => (bool) $form_state->getValue('show_sent_by'),
        'expected_occurrences' => (int) $form_state->getValue('expected_occurrences'),
        'sheet_order' => (int) $form_state->getValue('sheet_order'),
      ]);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($taskId === NULL
      ? $this->t('Added the task “@name”: @how_often.', ['@name' => $task['name'], '@how_often' => $task['how_often']])
      : $this->t('Saved “@name”.', ['@name' => $task['name']]));
    $form_state->setRedirect('bible_admin.tasks');
  }

  /**
   * A days-before box: a whole number, or NULL when left empty.
   */
  private function days(mixed $value): ?int {
    return $value === NULL || $value === '' ? NULL : (int) $value;
  }

}
