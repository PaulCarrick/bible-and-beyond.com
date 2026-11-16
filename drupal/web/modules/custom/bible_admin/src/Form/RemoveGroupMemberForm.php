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
 * Asks before removing a member from a group (their site account, if any, stays).
 */
class RemoveGroupMemberForm extends ConfirmFormBase {

  protected ?array $group = NULL;

  protected ?array $member = NULL;

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_remove_group_member';
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
    $form_state->set('group_id', (int) $this->group['id']);
    $form_state->set('member_id', (int) $this->member['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Remove @name from “@group”?', [
      '@name' => ($this->member['name'] ?? '') ?: ($this->member['email'] ?? ''),
      '@group' => $this->group['name'] ?? '',
    ]);
  }

  public function getDescription() {
    return $this->t('They get no more messages from this group. Their site account, if they have one, stays. You can add them again later.');
  }

  public function getConfirmText() {
    return $this->t('Remove');
  }

  public function getCancelUrl(): Url {
    return $this->group ? Url::fromRoute('bible_admin.group', ['group_id' => $this->group['id']]) : Url::fromRoute('bible_admin.groups');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $form_state->get('group_id');
    try {
      $member = $this->manager->removeGroupMember($groupId, (int) $form_state->get('member_id'));
      $this->messenger()->addStatus($this->t('Removed @name.', ['@name' => $member['name'] ?: $member['email']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
  }

}
