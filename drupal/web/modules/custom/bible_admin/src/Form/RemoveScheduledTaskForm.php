<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Asks before removing a scheduled task (the task itself stays).
 */
class RemoveScheduledTaskForm extends ConfirmFormBase {

  private ?array $schedule = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_remove_scheduled_task';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $schedule_id = NULL): array {
    try {
      $this->schedule = $this->manager->getScheduledTask((int) $schedule_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the scheduled tasks'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('schedule_id', (int) $this->schedule['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Remove “@task” for @person on @date?', [
      '@task' => $this->schedule['task_name'] ?? '',
      '@person' => $this->schedule['user_label'] ?? '',
      '@date' => $this->dateLabel($this->schedule['on_date'] ?? ''),
    ]);
  }

  public function getDescription() {
    return $this->t('The task itself stays; only this date for this person is removed.');
  }

  public function getConfirmText() {
    return $this->t('Remove');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.scheduled_tasks');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $schedule = $this->manager->removeScheduledTask((int) $form_state->get('schedule_id'));
      $this->messenger()->addStatus($this->t('Removed “@task” for @person on @date.', [
        '@task' => $schedule['task_name'],
        '@person' => $schedule['user_label'],
        '@date' => $this->dateLabel($schedule['on_date']),
      ]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
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
