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
 * Asks before removing a group's scheduled message (what it already sent stays in the group's record).
 */
class RemoveGroupScheduleForm extends ConfirmFormBase {

  protected ?array $schedule = NULL;

  protected int $groupId = 0;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_remove_group_schedule';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', string $schedule_id = ''): array {
    $this->groupId = (int) $group_id;
    try {
      $this->schedule = $this->manager->getGroupSchedule((int) $group_id, (int) $schedule_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the group'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('schedule_id', (int) $this->schedule['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    $what = match ($this->schedule['kind'] ?? 'message') {
      'verse' => $this->t('the scheduled verse card'),
      'picture' => $this->t('the scheduled picture message “@subject”', ['@subject' => $this->schedule['subject'] ?? '']),
      default => $this->t('the scheduled message “@subject”', ['@subject' => $this->schedule['subject'] ?? '']),
    };
    return $this->t('Remove @what?', ['@what' => $what]);
  }

  public function getDescription() {
    return $this->t('@when. Nothing more is sent by it; what it sent already stays in the group\'s record.', ['@when' => $this->schedule['description'] ?? '']);
  }

  public function getConfirmText() {
    return $this->t('Remove');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.group', ['group_id' => $this->groupId]);
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $this->manager->removeGroupSchedule($this->groupId, (int) $form_state->get('schedule_id'));
      $this->messenger()->addStatus($this->t('Removed the scheduled email.'));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.group', ['group_id' => $this->groupId]);
  }

}
