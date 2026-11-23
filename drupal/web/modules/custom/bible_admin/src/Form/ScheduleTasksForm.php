<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Schedule tasks (added 2026-11-23 at the owner's request): several tasks on one date at once. Choose the date; the
 * tasks that fall on it (among their next four dates) are listed, each with + to add a row for it (several rows for
 * the same task when it needs several people); each row chooses its site user and an optional note, and − removes
 * it. The list and the rows follow the choices by AJAX (with an Update the list button
 * when JavaScript is off). All are scheduled together, or none if one has a problem.
 */
class ScheduleTasksForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_schedule_tasks';
  }

  public function buildForm(array $form, FormStateInterface $form_state): array {
    $form['#cache'] = ['max-age' => 0];
    $onDate = (string) ($form_state->getValue('on_date') ?? $this->soonestDate());
    $ajax = ['callback' => '::refreshChoices', 'wrapper' => 'schedule-tasks-choices', 'event' => 'change'];

    $form['on_date'] = [
      '#type' => 'date',
      '#title' => $this->t('Date'),
      '#default_value' => $onDate,
      '#ajax' => $ajax,
    ];
    // Without JavaScript the list is brought up to date with this button.
    $form['update'] = [
      '#type' => 'submit',
      '#value' => $this->t('Update the list'),
      '#name' => 'update',
      '#submit' => ['::rebuild'],
      '#attributes' => ['class' => ['js-hide']],
    ];
    $form['choices'] = [
      '#type' => 'container',
      '#attributes' => ['id' => 'schedule-tasks-choices'],
    ];

    $day = \DateTimeImmutable::createFromFormat('!Y-m-d', $onDate);
    if ($day === FALSE || $day->format('Y-m-d') !== $onDate) {
      $form['choices']['message'] = ['#markup' => '<p>' . $this->t('Choose a date.') . '</p>'];
      return $form;
    }
    try {
      $options = $this->manager->taskDayOptions($onDate);
    }
    catch (BibleManagerException $exception) {
      $form['choices']['message'] = ['#markup' => '<p>' . $this->t('@message', ['@message' => $exception->getMessage()]) . '</p>'];
      return $form;
    }
    if (!$options['tasks']) {
      $form['choices']['message'] = [
        '#markup' => '<p>' . $this->t('No task falls on @day among its next four dates. Choose another date, or add or change a task on the <a href=":tasks">Tasks</a> page.', [
          '@day' => $options['label'],
          ':tasks' => Url::fromRoute('bible_admin.tasks')->toString(),
        ]) . '</p>',
      ];
      return $form;
    }

    $taskNames = [];
    foreach ($options['tasks'] as $task) {
      $taskNames[(int) $task['id']] = $task['name'];
    }
    // The rows chosen so far, by a key that never changes (so typing in one row stays with it when another is
    // removed): row key => task id. A task may have several rows (two people for Baked Goods, say; 2026-11-23).
    // A new date starts afresh.
    if ($form_state->get('rows_date') !== $onDate) {
      $form_state->set('rows', []);
      $form_state->set('rows_date', $onDate);
    }
    $rows = array_filter((array) $form_state->get('rows'), fn ($taskId) => isset($taskNames[$taskId]));
    $form_state->set('rows', $rows);

    $form['choices']['tasks'] = [
      '#type' => 'table',
      '#caption' => $this->t('Tasks on @day', ['@day' => $options['label']]),
      '#header' => [$this->t('Task'), $this->t('Already scheduled'), $this->t('Add')],
    ];
    foreach ($options['tasks'] as $task) {
      $taskId = (int) $task['id'];
      $form['choices']['tasks'][$taskId]['name'] = ['#plain_text' => $task['name']];
      $form['choices']['tasks'][$taskId]['already'] = ['#plain_text' => $task['scheduled_for'] ? implode(', ', $task['scheduled_for']) : ''];
      $form['choices']['tasks'][$taskId]['add'] = [
        '#type' => 'submit',
        '#value' => '+',
        '#name' => 'add_task_' . $taskId,
        '#task_id' => $taskId,
        '#submit' => ['::addRow'],
        '#ajax' => ['callback' => '::refreshChoices', 'wrapper' => 'schedule-tasks-choices'],
        '#attributes' => [
          'class' => ['button--small'],
          'title' => $this->t('Add a row for @task', ['@task' => $task['name']]),
          'aria-label' => $this->t('Add a row for @task', ['@task' => $task['name']]),
        ],
      ];
    }
    $form['choices']['help'] = [
      '#markup' => '<p class="description">' . $this->t('Press + beside a task to add a row for it; press it again for another person on the same task.') . '</p>',
    ];
    if (!$rows) {
      return $form;
    }
    $users = [];
    foreach ($options['users'] as $user) {
      $users[(int) $user['id']] = $user['label'];
    }
    $form['choices']['assignments'] = [
      '#type' => 'table',
      '#header' => [$this->t('Task'), $this->t('Site user'), $this->t('Note (optional)'), $this->t('Remove')],
    ];
    foreach ($rows as $key => $taskId) {
      $form['choices']['assignments'][$key]['task'] = ['#plain_text' => $taskNames[$taskId]];
      $form['choices']['assignments'][$key]['user_id'] = [
        '#type' => 'select',
        '#title' => $this->t('Site user for @task', ['@task' => $taskNames[$taskId]]),
        '#title_display' => 'invisible',
        '#options' => $users,
        '#empty_option' => $this->t('- Choose a site user -'),
      ];
      $form['choices']['assignments'][$key]['note'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Note for @task', ['@task' => $taskNames[$taskId]]),
        '#title_display' => 'invisible',
        '#maxlength' => 500,
        '#size' => 30,
      ];
      $form['choices']['assignments'][$key]['remove'] = [
        '#type' => 'submit',
        '#value' => '−',
        '#name' => 'remove_row_' . $key,
        '#row_key' => $key,
        '#submit' => ['::removeRow'],
        '#ajax' => ['callback' => '::refreshChoices', 'wrapper' => 'schedule-tasks-choices'],
        '#attributes' => [
          'class' => ['button--small'],
          'title' => $this->t('Remove this row for @task', ['@task' => $taskNames[$taskId]]),
          'aria-label' => $this->t('Remove this row for @task', ['@task' => $taskNames[$taskId]]),
        ],
      ];
    }
    $form['choices']['actions'] = ['#type' => 'actions'];
    $form['choices']['actions']['submit'] = [
      '#type' => 'submit',
      '#name' => 'schedule',
      '#value' => $this->formatPlural(count($rows), 'Schedule the task', 'Schedule the @count tasks'),
      '#button_type' => 'primary',
    ];
    return $form;
  }

  /**
   * "+" beside a task: a new row for it, with a key no row has had.
   */
  public function addRow(array &$form, FormStateInterface $form_state): void {
    $rows = (array) $form_state->get('rows');
    $next = (int) $form_state->get('next_row') + 1;
    $form_state->set('next_row', $next);
    $rows['row' . $next] = (int) ($form_state->getTriggeringElement()['#task_id'] ?? 0);
    $form_state->set('rows', $rows);
    $form_state->setRebuild();
  }

  /**
   * "−" on a row: it goes; the others keep what was typed in them.
   */
  public function removeRow(array &$form, FormStateInterface $form_state): void {
    $rows = (array) $form_state->get('rows');
    unset($rows[$form_state->getTriggeringElement()['#row_key'] ?? '']);
    $form_state->set('rows', $rows);
    $form_state->setRebuild();
  }

  public function refreshChoices(array $form, FormStateInterface $form_state): array {
    return $form['choices'];
  }

  public function rebuild(array &$form, FormStateInterface $form_state): void {
    $form_state->setRebuild();
  }

  public function validateForm(array &$form, FormStateInterface $form_state): void {
    if (($form_state->getTriggeringElement()['#name'] ?? '') !== 'schedule') {
      return;
    }
    foreach ((array) $form_state->getValue('assignments', []) as $key => $row) {
      if (empty($row['user_id'])) {
        $form_state->setErrorByName('assignments][' . $key . '][user_id', $this->t('Choose the site user for @task.', [
          '@task' => $form['choices']['assignments'][$key]['task']['#plain_text'] ?? $key,
        ]));
      }
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    if (($form_state->getTriggeringElement()['#name'] ?? '') !== 'schedule') {
      $form_state->setRebuild();
      return;
    }
    $onDate = (string) $form_state->getValue('on_date');
    $items = [];
    $rows = (array) $form_state->get('rows');
    foreach ((array) $form_state->getValue('assignments', []) as $key => $row) {
      if (!isset($rows[$key])) {
        continue;
      }
      $items[] = [
        'task_id' => (int) $rows[$key],
        'user_id' => (int) $row['user_id'],
        'note' => ['text' => (string) ($row['note'] ?? '')],
      ];
    }
    try {
      $added = $this->manager->addScheduledTasks($onDate, $items);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->formatPlural(count($added), 'Scheduled 1 task for @day.', 'Scheduled @count tasks for @day.', [
      '@day' => $this->longDay($onDate),
    ]));
    $form_state->setRedirect('bible_admin.scheduled_tasks');
  }

  /**
   * The date the form opens on: the soonest next date of this user's tasks, else today (their time zone).
   */
  private function soonestDate(): string {
    $today = (new \DateTimeImmutable('now', new \DateTimeZone($this->currentUser()->getTimeZone() ?: 'UTC')))->format('Y-m-d');
    try {
      $dates = array_filter(array_column($this->manager->listTasks(), 'next_date'), fn ($day) => $day >= $today);
    }
    catch (BibleManagerException) {
      $dates = [];
    }
    return $dates ? min($dates) : $today;
  }

  /**
   * A day such as "Sunday, November 29, 2026" (a date with no time, so no time zone change).
   */
  private function longDay(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $date->format('l, F j, Y');
  }

}
