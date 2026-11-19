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
 * Adds a task (belonging to the user adding it) or changes one: a name, a formatted description, how often it
 * comes round (every week on a day, every two weeks from a first date, or every month on a day) and the words of
 * its first and second notifications (formatted, in the group emails' editor; not sent yet).
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

    $form['recurrence'] = [
      '#type' => 'fieldset',
      '#title' => $this->t('How often'),
    ];
    $form['recurrence']['repeat'] = [
      '#type' => 'radios',
      '#title' => $this->t('Comes round'),
      '#title_display' => 'invisible',
      '#options' => [
        'weekly' => $this->t('Every week'),
        'biweekly' => $this->t('Every two weeks'),
        'monthly' => $this->t('Every month'),
      ],
      '#default_value' => $task['repeat'] ?? 'weekly',
      '#required' => TRUE,
    ];
    $form['recurrence']['weekday'] = [
      '#type' => 'select',
      '#title' => $this->t('On'),
      '#options' => [
        0 => $this->t('Monday'),
        1 => $this->t('Tuesday'),
        2 => $this->t('Wednesday'),
        3 => $this->t('Thursday'),
        4 => $this->t('Friday'),
        5 => $this->t('Saturday'),
        6 => $this->t('Sunday'),
      ],
      '#default_value' => $task['weekday'] ?? NULL,
      '#empty_option' => $this->t('- Choose a day -'),
      '#states' => [
        'visible' => [':input[name="repeat"]' => ['value' => 'weekly']],
        'required' => [':input[name="repeat"]' => ['value' => 'weekly']],
      ],
    ];
    $form['recurrence']['first_date'] = [
      '#type' => 'date',
      '#title' => $this->t('First date'),
      '#default_value' => $task['first_date'] ?? '',
      '#description' => $this->t('The task comes round on this day and every two weeks after it, on the same day of the week.'),
      '#states' => [
        'visible' => [':input[name="repeat"]' => ['value' => 'biweekly']],
        'required' => [':input[name="repeat"]' => ['value' => 'biweekly']],
      ],
    ];
    $form['recurrence']['day_of_month'] = [
      '#type' => 'number',
      '#title' => $this->t('Day of the month'),
      '#min' => 1,
      '#max' => 31,
      '#default_value' => $task['day_of_month'] ?? NULL,
      '#description' => $this->t('1 to 31. The 29th, 30th and 31st mean the last day in shorter months.'),
      '#states' => [
        'visible' => [':input[name="repeat"]' => ['value' => 'monthly']],
        'required' => [':input[name="repeat"]' => ['value' => 'monthly']],
      ],
    ];

    $form['first_notification'] = GroupEditor::field((string) $this->t('First notification'), (string) ($task['first_notification_html'] ?? ''), 4, FALSE);
    $form['second_notification'] = GroupEditor::field((string) $this->t('Second notification'), (string) ($task['second_notification_html'] ?? ''), 4, FALSE);

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
    // #states only marks the fields required in the browser; the field of the chosen repeat is checked here.
    $repeat = $form_state->getValue('repeat');
    if ($repeat === 'weekly' && (string) $form_state->getValue('weekday') === '') {
      $form_state->setErrorByName('weekday', $this->t('Choose the day of the week.'));
    }
    if ($repeat === 'biweekly' && (string) $form_state->getValue('first_date') === '') {
      $form_state->setErrorByName('first_date', $this->t('Choose the first date.'));
    }
    if ($repeat === 'monthly' && (string) $form_state->getValue('day_of_month') === '') {
      $form_state->setErrorByName('day_of_month', $this->t('Choose a day of the month from 1 to 31.'));
    }
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $taskId = $form_state->get('task_id');
    $repeat = (string) $form_state->getValue('repeat');
    try {
      $task = $this->manager->saveTask($taskId === NULL ? NULL : (int) $taskId, [
        'name' => (string) $form_state->getValue('name'),
        'description' => GroupEditor::value($form_state->getValue('description')),
        'repeat' => $repeat,
        'weekday' => $repeat === 'weekly' ? (int) $form_state->getValue('weekday') : NULL,
        'first_date' => $repeat === 'biweekly' ? (string) $form_state->getValue('first_date') : NULL,
        'day_of_month' => $repeat === 'monthly' ? (int) $form_state->getValue('day_of_month') : NULL,
        'first_notification' => GroupEditor::value($form_state->getValue('first_notification')),
        'second_notification' => GroupEditor::value($form_state->getValue('second_notification')),
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

}
