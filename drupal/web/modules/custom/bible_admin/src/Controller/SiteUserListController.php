<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\Form\SiteUserSearchForm;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Pager\PagerManagerInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\RequestStack;

/**
 * The list of the main site's accounts (its visitors, not Drupal users), with a search and pages.
 */
class SiteUserListController extends ControllerBase {

  public function __construct(
    private readonly BibleManager $manager,
    private readonly PagerManagerInterface $pagerManager,
    private readonly DateFormatterInterface $dateFormatter,
    private readonly RequestStack $requestStack,
  ) {}

  public static function create(ContainerInterface $container): static {
    return new static(
      $container->get('bible_admin.manager'),
      $container->get('pager.manager'),
      $container->get('date.formatter'),
      $container->get('request_stack'),
    );
  }

  public function build(): array {
    $query = trim((string) $this->requestStack->getCurrentRequest()->query->get('query', ''));
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('These are the accounts of the public site, bible-and-beyond.com: its visitors, who set them up to keep notes and receive devotional emails. They are not Drupal users.'),
      ],
      'search' => $this->formBuilder()->getForm(SiteUserSearchForm::class, $query),
    ];

    try {
      $listing = $this->manager->listSiteUsers($query, $this->pagerManager->findPage() + 1);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $this->pagerManager->createPager((int) $listing['total'], (int) $listing['per_page']);

    $build['count'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $query === ''
        ? $this->formatPlural((int) $listing['total'], 'One account.', '@count accounts.')
        : $this->formatPlural((int) $listing['total'], 'One account matches.', '@count accounts match.'),
    ];

    $rows = [];
    foreach ($listing['users'] as $user) {
      $links = [
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.site_user_edit', ['user_id' => $user['id']])],
        ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.site_user_delete', ['user_id' => $user['id']])],
      ];
      $name = trim(($user['first_name'] ?? '') . ' ' . ($user['last_name'] ?? ''));
      $rows[] = [
        ['data' => ['#plain_text' => $name]],
        // A closed account (its owner closed it on My account) says so after its address.
        // An account with no address logs in with its phone (2026-11-17); a closed one says so after it.
        ['data' => ['#plain_text' => ($user['email'] !== '' ? $user['email'] : (string) $this->t('(none: logs in with phone)')) . (!empty($user['closed']) ? ' ' . $this->t('(closed)') : '')]],
        ['data' => ['#plain_text' => $user['phone'] ?? '']],
        ['data' => ['#plain_text' => $user['email_verified'] ? $this->t('Yes') : $this->t('No')]],
        ['data' => ['#plain_text' => $user['open_ai_queries'] ? $this->t('Yes') : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['use_conversations']) ? $this->t('Yes') : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['get_conversation_posts']) ? $this->t('Yes') : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['see_private_prayers']) ? $this->t('Yes') : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['use_maps']) ? $this->t('Yes (@count marks)', ['@count' => number_format((int) ($user['map_mark_count'] ?? 0))]) : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['share_lists']) ? $this->t('Yes (@count shared)', ['@count' => number_format((int) ($user['shared_list_count'] ?? 0))]) : $this->t('No')]],
        ['data' => ['#plain_text' => !empty($user['sms_opt_in']) ? $this->t('Yes') : (!empty($user['sms_stopped']) ? $this->t('Stopped') : $this->t('No'))]],
        ['data' => ['#plain_text' => number_format((int) $user['note_count'])]],
        ['data' => ['#plain_text' => $this->formatDate($user['created_at'])]],
        ['data' => ['#plain_text' => $user['last_login_at'] ? $this->formatDate($user['last_login_at']) : $this->t('Never')]],
        ['data' => ['#type' => 'operations', '#links' => $links]],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Name'),
        $this->t('Email'),
        $this->t('Phone'),
        $this->t('Email confirmed'),
        $this->t('Open AI queries'),
        $this->t('Conversations'),
        $this->t('Gets posts'),
        $this->t('Private prayers'),
        $this->t('Maps'),
        $this->t('Share lists'),
        $this->t('Texts'),
        $this->t('Notes'),
        $this->t('Set up'),
        $this->t('Last login'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $query === '' ? $this->t('There are no accounts yet.') : $this->t('No account matches.'),
    ];
    $build['pager'] = ['#type' => 'pager'];
    return $build;
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }

}
