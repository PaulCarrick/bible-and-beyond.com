<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
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
      'description' => $group['description'] !== '' ? ['#type' => 'html_tag', '#tag' => 'p', '#value' => $group['description'], '#attributes' => ['style' => 'white-space: pre-wrap;']] : [],
      'leader' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Led by @name. Replies to its emails go to @address.', [
          '@name' => $group['owner_name'] ?: $this->t('(no name)'),
          '@address' => $group['owner_email'] ?: $this->t('(no address: set one on your Drupal account)'),
        ]),
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
      $links[] = ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.group_member_remove', $id + ['member_id' => $member['id']])];
      $rows[] = [
        ['data' => ['#plain_text' => $member['name'] !== '' ? $member['name'] : '—']],
        ['data' => ['#plain_text' => $member['email']]],
        ['data' => ['#plain_text' => $member['phone']]],
        ['data' => ['#plain_text' => (string) ($member['is_account'] ? $this->t('Site account') : $this->t('Contact'))]],
        ['data' => ['#plain_text' => $member['receives']]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }
    $build['members'] = [
      '#type' => 'table',
      '#header' => [$this->t('Name'), $this->t('Email'), $this->t('Phone'), $this->t('Kind'), $this->t('Gets messages by'), $this->t('Operations')],
      '#rows' => $rows,
      '#empty' => $this->t('No members yet. Use "Add a member".'),
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
      ];
    }
    $build['sent_heading'] = ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->t('Sent')];
    $build['sent'] = [
      '#type' => 'table',
      '#header' => [$this->t('When (UTC)'), $this->t('Kind'), $this->t('Subject'), $this->t('Reached'), $this->t('By')],
      '#rows' => $sent,
      '#empty' => $this->t('Nothing has been sent to this group yet.'),
    ];
    $build['back'] = $back;
    return $build;
  }

}
