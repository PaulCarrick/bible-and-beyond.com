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
 * Gives a task to a site user on a date (Schedule beside a task), or changes who and when for a scheduled task:
 * two selects, the site user and one of the task's next four dates (a weekly Sunday task offers the next four
 * Sundays; the owner's request, 2026-11-19). Changing one keeps its own date in the list even when it has passed.
 * An optional Note (the group emails' editor; 2026-11-22) is added under the task's notification in that person's
 * reminders; [FIRST_NAME], [LAST_NAME] and [FULL_NAME] in it are replaced with their name.
 */
class ScheduledTaskForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_scheduled_task';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $task_id = NULL, ?string $schedule_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $schedule = NULL;
    try {
      if ($schedule_id !== NULL) {
        $schedule = $this->manager->getScheduledTask((int) $schedule_id);
        $task_id = (string) $schedule['task_id'];
      }
      $options = $this->manager->taskScheduleOptions((int) $task_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the scheduled tasks'), '#url' => Url::fromRoute('bible_admin.scheduled_tasks')]];
    }
    $task = $options['task'];
    $form_state->set('task_id', (int) $task['id']);
    if ($schedule !== NULL) {
      $form_state->set('schedule_id', (int) $schedule['id']);
    }

    $form['task'] = [
      '#type' => 'item',
      '#title' => $this->t('Task'),
      '#markup' => $this->t('@name: @how_often', ['@name' => $task['name'], '@how_often' => $task['how_often']]),
    ];

    $users = [];
    foreach ($options['users'] as $user) {
      $users[(int) $user['id']] = $user['label'];
    }
    if ($schedule !== NULL && !isset($users[(int) $schedule['user_id']])) {
      $users[(int) $schedule['user_id']] = $schedule['user_label'];
    }
    $form['user_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Site user'),
      '#options' => $users,
      '#empty_option' => $this->t('- Choose a site user -'),
      '#default_value' => $schedule['user_id'] ?? NULL,
      '#required' => TRUE,
    ];

    $dates = [];
    foreach ($options['dates'] as $date) {
      $dates[$date['value']] = $date['label'];
    }
    if ($schedule !== NULL && !isset($dates[$schedule['on_date']])) {
      $dates = [$schedule['on_date'] => $this->t('@date (its date now)', ['@date' => $this->dateLabel($schedule['on_date'])])] + $dates;
    }
    $form['on_date'] = [
      '#type' => 'select',
      '#title' => $this->t('Date'),
      '#options' => $dates,
      '#default_value' => $schedule['on_date'] ?? array_key_first($dates),
      '#required' => TRUE,
      '#description' => $this->t('The next date the task falls on, or one of the three after it.'),
    ];

    $form['note'] = GroupEditor::field(
      (string) $this->t('Note'),
      (string) ($schedule['note_html'] ?? ''),
      4,
      FALSE,
      (string) $this->t('Optional. Added under the task’s notification in this person’s reminder emails and texts. [FIRST_NAME], [LAST_NAME] and [FULL_NAME] are replaced with their name (“friend” when the account has no name); they work in the task’s notifications too.'),
    );

    $form['confirmed'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Confirmed'),
      '#default_value' => !empty($schedule['confirmed']),
      '#description' => $this->t('Tick this once it is confirmed, for example when the person has said they will do it. A new scheduled task starts unconfirmed.'),
    ];

    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $schedule === NULL ? $this->t('Schedule') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => $schedule === NULL ? Url::fromRoute('bible_admin.tasks') : Url::fromRoute('bible_admin.scheduled_tasks'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $scheduleId = $form_state->get('schedule_id');
    $userId = (int) $form_state->getValue('user_id');
    $onDate = (string) $form_state->getValue('on_date');
    $note = GroupEditor::value($form_state->getValue('note'));
    $confirmed = (bool) $form_state->getValue('confirmed');
    try {
      $schedule = $scheduleId === NULL
        ? $this->manager->addScheduledTask((int) $form_state->get('task_id'), $userId, $onDate, $note, $confirmed)
        : $this->manager->updateScheduledTask((int) $scheduleId, $userId, $onDate, $note, $confirmed);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('“@task” is scheduled for @person on @date.', [
      '@task' => $schedule['task_name'],
      '@person' => $schedule['user_label'],
      '@date' => $this->dateLabel($schedule['on_date']),
    ]));
    // Ticking Confirmed tells the member (member_task_requests.tell_confirmed): say how it went.
    if (!empty($schedule['confirmation_notice'])) {
      $this->messenger()->addStatus($this->t('Confirmed. @notice', ['@notice' => $schedule['confirmation_notice']]));
    }
    $form_state->setRedirect('bible_admin.scheduled_tasks');
  }

  /**
   * A day such as "Sunday, November 22, 2026" (a date with no time, so no time zone change).
   */
  private function dateLabel(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $date->format('l, F j, Y');
  }

}
