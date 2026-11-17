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
 * An email to one member of a group (added 2026-11-17 at the owner's request: the member's address in the
 * group's list is a link that opens a box with Send and Cancel). On the group page it opens in a dialog
 * (core/drupal.dialog.ajax); without JavaScript it is a page of its own. Send emails the words to that member
 * only (groups.email_member: the leader as the visible To, the member the hidden recipient, Reply-To the
 * leader); Cancel closes the box (the "dialog-cancel" class) or goes back to the group, sending nothing.
 */
class GroupMemberEmailForm extends FormBase {


  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_group_member_email';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $group_id = '', string $member_id = ''): array {
    $form['#cache'] = ['max-age' => 0];
    try {
      $group = $this->manager->getGroup((int) $group_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')]];
    }
    $back = Url::fromRoute('bible_admin.group', ['group_id' => $group['id']]);
    $member = NULL;
    foreach ($group['members'] as $each) {
      if ((int) $each['id'] === (int) $member_id) {
        $member = $each;
      }
    }
    if ($member === NULL) {
      $this->messenger()->addError($this->t('That member is not in the group (they may have been removed).'));
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the group'), '#url' => $back]];
    }
    $form_state->set('group_id', (int) $group['id']);
    $form_state->set('member_id', (int) $member['id']);
    $name = $member['name'] !== '' ? $member['name'] : $member['email'];

    $form['to'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('To @name only, by email. Replies go to @address.', [
        '@name' => $name,
        '@address' => $group['owner_email'] ?: $this->t('the site\'s address (set one on your Drupal account)'),
      ]),
    ];
    // The editor (GroupEditor: CKEditor 5, text format group_email; the owner's request, 2026-11-17). The ML
    // service cleans what it writes. Without the format, a plain box.
    $form['text'] = GroupEditor::field((string) $this->t('Message'), '', 8, TRUE);
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Send'),
      '#button_type' => 'primary',
    ];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => $back,
      '#attributes' => ['class' => ['button', 'dialog-cancel']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $form_state->get('group_id');
    // From the editor: HTML; from the plain box: text.
    $details = GroupEditor::value($form_state->getValue('text'));
    try {
      $member = $this->manager->emailGroupMember($groupId, (int) $form_state->get('member_id'), $details);
      $this->messenger()->addStatus($this->t('Your message was emailed to @name.', ['@name' => $member['name'] ?: $this->t('the member')]));
      $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
    }
    catch (BibleManagerException $exception) {
      // Keep the words, so nothing typed is lost.
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
    }
  }

}
