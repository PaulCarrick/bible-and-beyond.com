<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\bible_admin\SavedCardChoice;
use Drupal\Core\Datetime\DrupalDateTime;
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
 *
 * Send at (added 2026-11-18 at the owner's request): a date and time, now to start with. Left at now (or any
 * time up to a minute from now) it goes at once; a later time keeps it as a one-time scheduled email to that
 * member, in the group's Scheduled emails, which the five-minute job sends then (group_schedules.py). The time
 * is in the leader's own Drupal time zone.
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
    // The email's subject (added 2026-11-18 at the owner's request), starting with the one it had before.
    $form['subject'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Subject'),
      '#default_value' => (string) $this->t('A message from @leader (@group)', [
        '@leader' => $group['owner_name'] ?: $this->t('your group\'s leader'),
        '@group' => $group['name'],
      ]),
      '#maxlength' => 200,
      '#required' => TRUE,
    ];
    // The editor (GroupEditor: CKEditor 5, text format group_email; the owner's request, 2026-11-17). The ML
    // service cleans what it writes. Without the format, a plain box.
    $form['text'] = GroupEditor::field((string) $this->t('Message'), '', 8, TRUE);
    // The signature after the words (2026-11-19, the owner's request: "Add the signature select to Email a member
    // too"): one of the group leader's signatures, or none.
    $signatures = [];
    try {
      foreach ($this->manager->listLeaderSignatures($group) as $signature) {
        $signatures[(int) $signature['id']] = $signature['name'];
      }
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form['signature_id'] = [
      '#type' => 'select',
      '#title' => $this->t('Signature'),
      '#options' => ['' => $this->t('- No signature -')] + $signatures,
      '#default_value' => '',
      '#description' => $signatures
        ? $this->t('Added after your message.')
        : ((int) $group['owner_uid'] === (int) $this->currentUser()->id()
          ? $this->t('You have no signatures yet. Add one on the <a href=":url">Signatures</a> page.', [':url' => Url::fromRoute('bible_admin.signatures')->toString()])
          : $this->t('The group leader has no signatures yet.')),
    ];
    // One of the sender's saved verse cards (SavedCardChoice; 2026-11-26).
    $form['saved_card_box'] = SavedCardChoice::element($this->manager, $form_state);
    $zone = $this->timeZone();
    // Now, to the minute: with seconds the browser would only take times ending in those seconds.
    $now = new DrupalDateTime('now', $zone);
    $now->setTime((int) $now->format('G'), (int) $now->format('i'), 0);
    $form['send_at'] = [
      '#type' => 'datetime',
      '#title' => $this->t('Send at'),
      '#default_value' => $now,
      '#date_timezone' => $zone,
      '#date_increment' => 60,
      // Hours and minutes, no seconds.
      '#date_time_format' => 'H:i',
      '#required' => TRUE,
      '#description' => $this->t('Now, to start with: leave it to send the message at once, or choose a later date and time to send it then (@zone).', ['@zone' => $zone]),
    ];
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

  /**
   * The leader's own time zone (their Drupal account's, else the site's).
   */
  private function timeZone(): string {
    return $this->currentUser()->getTimeZone() ?: ($this->config('system.date')->get('timezone.default') ?: 'UTC');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $groupId = (int) $form_state->get('group_id');
    // From the editor: HTML; from the plain box: text.
    $details = GroupEditor::value($form_state->getValue('text'));
    $details['subject'] = trim((string) $form_state->getValue('subject'));
    $details['signature_id'] = (string) $form_state->getValue('signature_id');
    $details['saved_card'] = SavedCardChoice::value($form_state);
    // Up to a minute from now counts as now (the box was opened at "now" and the message written after).
    $sendAt = NULL;
    $when = $form_state->getValue('send_at');
    if ($when instanceof DrupalDateTime && $when->getTimestamp() > time() + 60) {
      $when->setTimezone(new \DateTimeZone($this->timeZone()));
      $sendAt = ['on_date' => $when->format('Y-m-d'), 'send_time' => $when->format('H:i'), 'timezone' => $this->timeZone()];
    }
    try {
      $member = $this->manager->emailGroupMember($groupId, (int) $form_state->get('member_id'), $details, $sendAt);
      $name = $member['name'] ?: $this->t('the member');
      if (isset($member['schedule'])) {
        $this->messenger()->addStatus($this->t('Your message to @name will be emailed on @when. It is under Scheduled emails, where you can remove it before then.', [
          '@name' => $name,
          '@when' => $member['schedule']['next_run_local'],
        ]));
      }
      else {
        $this->messenger()->addStatus($this->t('Your message was emailed to @name.', ['@name' => $name]));
      }
      $form_state->setRedirect('bible_admin.group', ['group_id' => $groupId]);
    }
    catch (BibleManagerException $exception) {
      // Keep the words, so nothing typed is lost.
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
    }
  }

}
