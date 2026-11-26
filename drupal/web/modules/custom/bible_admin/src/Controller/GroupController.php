<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\GroupEditor;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The Groups pages (groups.py): the list of the leader's groups, and one group with its members, the three
 * ways to send to them, and what was sent.
 */
class GroupController extends ControllerBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  /**
   * The groups this user leads (all groups for those who administer them), with Make a group.
   */
  public function list(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Groups of people you look after. Add people by their email address: someone with an account on the site gets your messages the way they chose on their My account page (email, text or both); anyone else gets email. Send a message, a random Bible verse card, or your own words on a picture to the whole group. Replies come to your own email address.'),
      ],
      'add' => [
        '#type' => 'link',
        '#title' => $this->t('Make a group'),
        '#url' => Url::fromRoute('bible_admin.group_add'),
        '#attributes' => ['class' => ['button', 'button--primary', 'button--small']],
      ],
    ];
    try {
      $groups = $this->manager->listGroups();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $showsLeader = $this->currentUser()->hasPermission('administer groups');
    $rows = [];
    foreach ($groups as $group) {
      $row = [
        ['data' => ['#type' => 'link', '#title' => $group['name'], '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group['id']])]],
        ['data' => ['#plain_text' => (string) $group['member_count']]],
        ['data' => ['#plain_text' => $group['last_sent_at'] ? substr($group['last_sent_at'], 0, 10) : (string) $this->t('Nothing yet')]],
      ];
      if ($showsLeader) {
        $row[] = ['data' => ['#plain_text' => $group['owner_name']]];
      }
      $rows[] = $row;
    }
    $header = [$this->t('Group'), $this->t('Members'), $this->t('Last message')];
    if ($showsLeader) {
      $header[] = $this->t('Leader');
    }
    $build['table'] = [
      '#type' => 'table',
      '#header' => $header,
      '#rows' => $rows,
      '#empty' => $this->t('You have no groups yet. Use "Make a group" to start one.'),
    ];
    return $build;
  }

  /**
   * The group's scheduled messages: when, what, the next time, how the last one went, Edit and Remove.
   */
  private function scheduleTable(array $group): array {
    $rows = [];
    foreach ($group['schedules'] ?? [] as $schedule) {
      $parameters = ['group_id' => $group['id'], 'schedule_id' => $schedule['id']];
      $toOne = !empty($schedule['member_id']);
      $what = $toOne ? $this->t('Message to @name only', ['@name' => $schedule['member_name'] ?: $this->t('one member')]) : match ($schedule['kind']) {
        'verse' => $this->t('Verse card'),
        'picture' => $this->t('Picture message: @subject', ['@subject' => $schedule['subject']]),
        default => $this->t('Message: @subject', ['@subject' => $schedule['subject']]),
      };
      if (!empty($schedule['saved_card_id'])) {
        $what = $this->t('@what, with a verse card', ['@what' => $what]);
      }
      if (!empty($schedule['signature_name'])) {
        $what = $this->t('@what, signed “@signature”', ['@what' => $what, '@signature' => $schedule['signature_name']]);
      }
      // Members who stopped it with the links in a scheduled email (this one, or all the group's scheduled
      // emails); they are still in the group (2026-11-17, the owner's request).
      if (!empty($schedule['stopped_count'])) {
        $what = $this->t('@what (@stopped)', [
          '@what' => $what,
          '@stopped' => $this->formatPlural($schedule['stopped_count'], '1 member stopped it', '@count members stopped it'),
        ]);
      }
      $rows[] = [
        ['data' => ['#plain_text' => $schedule['description']]],
        ['data' => ['#plain_text' => (string) $what]],
        ['data' => ['#plain_text' => $schedule['next_run_local'] ?? (string) $this->t('Done (it was sent once)')]],
        ['data' => ['#plain_text' => $schedule['last_result'] ?: '—']],
        // A message to one member (Send at on their Email box) can only be removed: write it again to change it.
        ['data' => ['#type' => 'operations', '#links' => $toOne ? [
          ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.group_schedule_remove', $parameters)],
        ] : [
          ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.group_schedule_edit', $parameters)],
          ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.group_schedule_remove', $parameters)],
          // Sends it now to the group's leader only, to check it (2026-11-17, the owner's request).
          ['title' => $this->t('Send a test'), 'url' => Url::fromRoute('bible_admin.group_schedule_test', $parameters)],
        ]]],
      ];
    }
    return [
      '#type' => 'table',
      '#header' => [$this->t('When'), $this->t('What'), $this->t('Next'), $this->t('Last time'), $this->t('Operations')],
      '#rows' => $rows,
      '#empty' => $this->t('Nothing scheduled. Use "Add a scheduled email" to send on a date, or every week or month.'),
    ];
  }

  /**
   * How the group's messages reach a member, with the scheduled emails they stopped (they stay in the group).
   */
  private function receives(array $member): string {
    $receives = $member['receives'];
    if ($member['stopped']) {
      return $receives;
    }
    if (!empty($member['schedules_stopped'])) {
      return $receives . ' ' . $this->t('(no scheduled emails: they stopped them all)');
    }
    if (!empty($member['stopped_schedules'])) {
      return $receives . ' ' . $this->formatPlural($member['stopped_schedules'], '(stopped 1 scheduled email)', '(stopped @count scheduled emails)');
    }
    return $receives;
  }

  /**
   * The copy kept of one email sent to the group (2026-11-18, the owner's request: "an exact copy of the email
   * sent (to, bcc, subject, contents: html if possible plain text otherwise)"): its headers, every address it
   * was emailed to, and the email itself. The HTML is shown in a sandboxed frame (no scripts, no access to this
   * page; links open in a new tab); without HTML, the plain text. Each member's copy had their own stop links,
   * so the copy kept shows a placeholder code in them.
   */
  public function sentCopy(string $group_id, string $message_id): array {
    $back = [
      '#type' => 'link',
      '#title' => $this->t('Back to the group'),
      '#url' => Url::fromRoute('bible_admin.group', ['group_id' => $group_id]),
    ];
    try {
      $copy = $this->manager->getGroupSentCopy((int) $group_id, (int) $message_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => $back];
    }
    $bcc = $copy['bcc'];
    $bccCell = $bcc
      ? ['#theme' => 'item_list', '#items' => array_map(fn ($address) => ['#plain_text' => $address], $bcc), '#attributes' => ['style' => 'margin: 0;']]
      : ['#plain_text' => (string) $this->t('Nobody: it went to the To address only.')];
    $header = fn (string $label, array $value) => [['data' => ['#plain_text' => $label], 'header' => TRUE], ['data' => $value]];
    $rows = [
      $header((string) $this->t('Sent (UTC)'), ['#plain_text' => str_replace('T', ' ', substr($copy['sent_at'], 0, 16)) . ' ' . $this->t('by @who', ['@who' => $copy['sent_by']])]),
      $header((string) $this->t('From'), ['#plain_text' => $copy['from']]),
      $header((string) $this->t('To'), ['#plain_text' => $copy['to']]),
      $header((string) $this->t('Reply-To'), ['#plain_text' => $copy['reply_to'] ?: '—']),
      $header((string) $this->formatPlural(count($bcc), 'Bcc (1 address)', 'Bcc (@count addresses)'), $bccCell),
      $header((string) $this->t('Subject'), ['#plain_text' => $copy['subject']]),
    ];
    $notes = [];
    // An email to one member (2026-11-18) has its address as the To and no Bcc.
    if ($bcc) {
      $notes[] = $this->t('Each address under Bcc got its own copy as a hidden recipient: no member saw another member\'s address.');
    }
    if ($copy['leader_copy']) {
      $notes[] = $this->t('The leader also got their own copy, with no stop links and a line saying how many it went to.');
    }
    if ($copy['texted']) {
      $notes[] = $this->formatPlural($copy['texted'], '1 member got it as a text message instead of or as well as this email.', '@count members got it as a text message instead of or as well as this email.');
    }
    $placeholder = $copy['stop_code_placeholder'];
    if (str_contains($copy['text'], $placeholder)) {
      $notes[] = $this->t('Each member\'s stop links carried their own code; here it shows as @code, which stops nothing.', ['@code' => $placeholder]);
    }

    $build = [
      '#cache' => ['max-age' => 0],
      'headers' => ['#type' => 'table', '#rows' => $rows, '#attributes' => ['class' => ['group-sent-copy-headers']]],
      'notes' => ['#theme' => 'item_list', '#items' => $notes],
    ];
    if ($copy['html'] !== NULL && $copy['html'] !== '') {
      // srcdoc is escaped as an attribute; the sandbox has no allow-scripts or allow-same-origin, so nothing in it
      // runs or reaches this page. Links open in a new tab (base target, allow-popups).
      $document = '<base target="_blank">' . $copy['html'];
      $build['email'] = [
        '#type' => 'html_tag',
        '#tag' => 'iframe',
        '#value' => '',
        '#attributes' => [
          'srcdoc' => $document,
          'sandbox' => 'allow-popups allow-popups-to-escape-sandbox',
          'referrerpolicy' => 'no-referrer',
          'title' => (string) $this->t('The email'),
          'style' => 'width: 100%; height: 70vh; border: 1px solid #ccc; background: #fff;',
        ],
      ];
      $build['text'] = [
        '#type' => 'details',
        '#title' => $this->t('Its plain-text copy'),
        'body' => ['#type' => 'html_tag', '#tag' => 'pre', 'content' => ['#plain_text' => $copy['text']], '#attributes' => ['style' => 'white-space: pre-wrap;']],
      ];
    }
    else {
      $build['email'] = [
        '#type' => 'html_tag',
        '#tag' => 'pre',
        'content' => ['#plain_text' => $copy['text']],
        '#attributes' => ['style' => 'white-space: pre-wrap; border: 1px solid #ccc; padding: 1em; background: #fff;'],
      ];
    }
    $build['back'] = $back;
    return $build;
  }

  public function title(string $group_id): string {
    try {
      return $this->manager->getGroup((int) $group_id)['name'];
    }
    catch (BibleManagerException) {
      return (string) $this->t('Group');
    }
  }

  /**
   * One group: what it is, the send buttons, the members (with Edit and Remove) and the messages sent.
   */
  public function view(string $group_id): array {
    $back = ['#type' => 'link', '#title' => $this->t('Back to the groups'), '#url' => Url::fromRoute('bible_admin.groups')];
    try {
      $group = $this->manager->getGroup((int) $group_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => $back];
    }
    $id = ['group_id' => $group['id']];
    $active = count(array_filter($group['members'], fn ($member) => !$member['stopped']));
    $button = fn (string $title, string $route, array $parameters, bool $primary = FALSE) => [
      '#type' => 'link',
      '#title' => $title,
      '#url' => Url::fromRoute($route, $parameters),
      '#attributes' => ['class' => array_filter(['button', 'button--small', $primary ? 'button--primary' : NULL])],
    ];

    $build = [
      '#cache' => ['max-age' => 0],
      // The leader's notes: from the editor (cleaned HTML; #markup filters it again), or plain text from before.
      'description' => $group['description'] === '' ? [] : (GroupEditor::isHtml($group['description'])
        ? ['#type' => 'container', '#attributes' => ['class' => ['group-notes']], 'notes' => ['#markup' => $group['description']]]
        : ['#type' => 'html_tag', '#tag' => 'p', '#value' => $group['description'], '#attributes' => ['style' => 'white-space: pre-wrap;']]),
      'leader' => [
        '#type' => 'container',
        '#attributes' => ['class' => ['group-leader'], 'style' => 'margin: 1em 0;'],
        'line' => [
          '#markup' => $this->t('Led by @name. Replies to its emails go to @address.', [
            '@name' => $group['owner_name'] ?: $this->t('(no name)'),
            '@address' => $group['owner_email'] ?: $this->t('(no address: set one on your Drupal account)'),
          ]),
        ],
        // Those who administer all groups can give it another leader (on Change the group; the owner asked for
        // the link here, 2026-11-16, as the choice was easy to miss there).
        'change' => $this->currentUser()->hasPermission('administer groups') ? [
          '#prefix' => ' ',
          '#type' => 'link',
          '#title' => $this->t('Change the leader'),
          '#url' => Url::fromRoute('bible_admin.group_edit', $id, ['fragment' => 'edit-leader']),
        ] : [],
      ],
      'send_heading' => ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->t('Send to the group')],
      'send_note' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->formatPlural($active, 'Goes to the one member who has not stopped the group\'s messages.', 'Goes to the @count members who have not stopped the group\'s messages.'),
      ],
      'send' => [
        '#type' => 'container',
        '#attributes' => ['class' => ['form-actions']],
        'message' => $button((string) $this->t('Send a message'), 'bible_admin.group_send', $id + ['kind' => 'message'], TRUE),
        'verse' => $button((string) $this->t('Send a verse card'), 'bible_admin.group_send', $id + ['kind' => 'verse']),
        'picture' => $button((string) $this->t('Send a picture message'), 'bible_admin.group_send', $id + ['kind' => 'picture']),
      ],
      'schedule_heading' => ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->t('Scheduled')],
      'schedule_actions' => [
        '#type' => 'container',
        '#attributes' => ['class' => ['form-actions']],
        'add' => $button((string) $this->t('Add a scheduled email'), 'bible_admin.group_schedule_add', $id, TRUE),
      ],
      'schedules' => $this->scheduleTable($group),
      'members_heading' => ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->t('Members (@count)', ['@count' => count($group['members'])])],
      'member_actions' => [
        '#type' => 'container',
        '#attributes' => ['class' => ['form-actions']],
        'add' => $button((string) $this->t('Add a member'), 'bible_admin.group_member_add', $id, TRUE),
        'edit' => $button((string) $this->t('Change the group'), 'bible_admin.group_edit', $id),
        'delete' => $button((string) $this->t('Delete the group'), 'bible_admin.group_delete', $id),
      ],
    ];

    $rows = [];
    foreach ($group['members'] as $member) {
      $links = [];
      if (!$member['is_account']) {
        $links[] = ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.group_member_edit', $id + ['member_id' => $member['id']])];
      }
      // The undo for scheduled emails the member stopped (2026-11-17, the owner's request).
      if (!empty($member['schedules_stopped']) || !empty($member['stopped_schedules'])) {
        $links[] = ['title' => $this->t('Start scheduled emails again'), 'url' => Url::fromRoute('bible_admin.group_member_restart_schedules', $id + ['member_id' => $member['id']])];
      }
      $links[] = ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.group_member_remove', $id + ['member_id' => $member['id']])];
      // The name of a member with a site account links to their entry on Site users, for those who may open
      // it (administer site users; a Group leader may not, and sees the name only). Contacts have no entry.
      $name = $member['name'] !== '' ? $member['name'] : '—';
      $nameCell = ['#plain_text' => $name];
      if ($member['is_account'] && !empty($member['user_id'])) {
        $siteUser = Url::fromRoute('bible_admin.site_user_edit', ['user_id' => $member['user_id']]);
        if ($siteUser->access()) {
          $nameCell = ['#type' => 'link', '#title' => $name, '#url' => $siteUser];
        }
      }
      // The address opens a box to email this member alone (GroupMemberEmailForm, in a dialog); not for a
      // member who stopped the group's messages or has not confirmed their address (it would be refused).
      $emailCell = ['#plain_text' => $member['email']];
      if ($member['email'] !== '' && !$member['stopped'] && ($member['confirmed'] ?? TRUE)) {
        $emailCell = [
          '#type' => 'link',
          '#title' => $member['email'],
          '#url' => Url::fromRoute('bible_admin.group_member_email', $id + ['member_id' => $member['id']]),
          '#attributes' => [
            'class' => ['use-ajax'],
            'data-dialog-type' => 'modal',
            'data-dialog-options' => json_encode(['width' => 600, 'title' => (string) $this->t('Email @name', ['@name' => $member['name'] ?: $member['email']])]),
            'title' => (string) $this->t('Email this member only'),
          ],
        ];
      }
      $rows[] = [
        ['data' => $nameCell],
        ['data' => $emailCell],
        ['data' => ['#plain_text' => $member['phone']]],
        ['data' => ['#plain_text' => (string) ($member['is_account'] ? $this->t('Site account') : $this->t('Contact'))]],
        ['data' => ['#plain_text' => $this->receives($member)]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }
    $build['members'] = [
      '#type' => 'table',
      '#header' => [$this->t('Name'), $this->t('Email'), $this->t('Phone'), $this->t('Kind'), $this->t('Gets messages by'), $this->t('Operations')],
      '#rows' => $rows,
      '#empty' => $this->t('No members yet. Use "Add a member".'),
      '#attached' => ['library' => ['core/drupal.dialog.ajax']],
    ];

    $sent = [];
    foreach ($group['sent'] as $message) {
      $kind = match ($message['kind']) {
        'verse' => $this->t('Verse card'),
        'picture' => $this->t('Picture message'),
        default => $this->t('Message'),
      };
      $sent[] = [
        str_replace('T', ' ', substr($message['sent_at'], 0, 16)),
        (string) $kind,
        $message['subject'],
        (string) $this->t('@emailed emailed, @texted texted@more', [
          '@emailed' => $message['emailed'],
          '@texted' => $message['texted'],
          '@more' => ($message['skipped'] ? ', ' . $message['skipped'] . ' skipped' : '') . ($message['failed'] ? ', ' . $message['failed'] . ' failed' : ''),
        ]),
        $message['sent_by'],
        // The copy kept of the email as it went out (2026-11-18, the owner's request); none for older messages
        // or a send that emailed nobody.
        ['data' => empty($message['has_copy']) ? ['#plain_text' => ''] : [
          '#type' => 'link',
          '#title' => $this->t('View'),
          '#url' => Url::fromRoute('bible_admin.group_sent_copy', $id + ['message_id' => $message['id']]),
          '#attributes' => ['title' => (string) $this->t('The email as it was sent')],
        ]],
      ];
    }
    $build['sent_heading'] = ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->t('Sent')];
    $build['sent'] = [
      '#type' => 'table',
      '#header' => [$this->t('When (UTC)'), $this->t('Kind'), $this->t('Subject'), $this->t('Reached'), $this->t('By'), $this->t('Email')],
      '#rows' => $sent,
      '#empty' => $this->t('Nothing has been sent to this group yet.'),
    ];
    $build['back'] = $back;
    return $build;
  }

}
