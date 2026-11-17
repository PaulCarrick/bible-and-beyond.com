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
 * "Start scheduled emails again" for a member who stopped some or all of the group's scheduled emails with the links
 * in them (added 2026-11-17 at the owner's request: an undo, instead of removing and adding them again). Asks first,
 * then clears both kinds of stop (groups.restart_schedules). The group's own stop link (everything) is not undone.
 */
class RestartMemberSchedulesForm extends ConfirmFormBase {

  protected ?array $group = NULL;

  protected ?array $member = NULL;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_restart_member_schedules';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', string $member_id = ''): array {
    try {
      $this->group = $this->manager->getGroup((int) $group_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    foreach ($this->group['members'] as $member) {
      if ((int) $member['id'] === (int) $member_id) {
        $this->member = $member;
      }
    }
    if ($this->member === NULL) {
      $this->messenger()->addError($this->t('That member is not in the group (they may have been removed).'));
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the group'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('member_id', (int) $this->member['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Start the scheduled emails again for @name?', ['@name' => ($this->member['name'] ?? '') ?: ($this->member['email'] ?? '')]);
  }

  public function getDescription() {
    $what = !empty($this->member['schedules_stopped'])
      ? $this->t('They stopped all of this group\'s scheduled emails.')
      : $this->formatPlural((int) ($this->member['stopped_schedules'] ?? 0), 'They stopped one of this group\'s scheduled emails.', 'They stopped @count of this group\'s scheduled emails.');
    return $what . ' ' . $this->t('They will get every scheduled email again, from the next one. They chose to stop them, so only do this if they asked you to.');
  }

  public function getConfirmText() {
    return $this->t('Start them again');
  }

  public function getCancelUrl(): Url {
    return $this->group ? Url::fromRoute('bible_admin.group', ['group_id' => $this->group['id']]) : Url::fromRoute('bible_admin.groups');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $this->group['id'];
    try {
      $member = $this->manager->restartGroupMemberSchedules($groupId, (int) $form_state->get('member_id'));
      $this->messenger()->addStatus($this->t('@name gets the scheduled emails again.', ['@name' => $member['name'] ?: $member['email']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
  }

}
