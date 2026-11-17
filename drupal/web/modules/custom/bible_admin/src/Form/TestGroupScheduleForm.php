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
 * "Send a test" of a group's scheduled email (added 2026-11-17 at the owner's request): sends it now to the
 * group's leader only, so they can check it (group_schedules.send_test). No member gets it, and the schedule's
 * next time is not changed.
 */
class TestGroupScheduleForm extends ConfirmFormBase {

  protected ?array $schedule = NULL;

  protected ?array $group = NULL;

  protected int $groupId = 0;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_test_group_schedule';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', string $schedule_id = ''): array {
    $this->groupId = (int) $group_id;
    try {
      $this->group = $this->manager->getGroup((int) $group_id);
      $this->schedule = $this->manager->getGroupSchedule((int) $group_id, (int) $schedule_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the group'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('schedule_id', (int) $this->schedule['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    if ($this->group['owner_email'] === '') {
      $this->messenger()->addWarning($this->t('The group\'s leader has no email address: set one on their Drupal account first.'));
      $form['actions']['submit']['#access'] = FALSE;
    }
    return $form;
  }

  public function getQuestion() {
    $what = match ($this->schedule['kind'] ?? 'message') {
      'verse' => $this->t('the scheduled verse card'),
      'picture' => $this->t('the scheduled picture message “@subject”', ['@subject' => $this->schedule['subject'] ?? '']),
      default => $this->t('the scheduled message “@subject”', ['@subject' => $this->schedule['subject'] ?? '']),
    };
    return $this->t('Send a test of @what?', ['@what' => $what]);
  }

  public function getDescription() {
    $description = $this->t('It goes now, by email, only to the group\'s leader (@address), marked as a test. No member gets it, and it still goes to the group at its time (@when).', [
      '@address' => ($this->group['owner_email'] ?? '') ?: $this->t('no address'),
      '@when' => $this->schedule['description'] ?? '',
    ]);
    if (in_array($this->schedule['kind'] ?? '', ['verse', 'picture'], TRUE)) {
      $description .= ' ' . $this->t('The picture is chosen at random each time, so the test shows one example.');
    }
    return $description;
  }

  public function getConfirmText() {
    return $this->t('Send the test');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.group', ['group_id' => $this->groupId]);
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $sent = $this->manager->testGroupSchedule($this->groupId, (int) $form_state->get('schedule_id'));
      $this->messenger()->addStatus($this->t('A test was emailed to @address. No member got it.', ['@address' => $sent['to']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.group', ['group_id' => $this->groupId]);
  }

}
