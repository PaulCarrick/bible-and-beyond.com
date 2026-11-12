<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\bible_admin\Form\ConversationSearchForm;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Pager\PagerManagerInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\RequestStack;

/**
 * The members' posts of Conversations on the public site, newest first, with a search and pages, so an
 * administrator can read them and remove one.
 */
class ConversationListController extends ControllerBase {

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
        '#value' => $this->t('These are the posts that members write on the Conversations page of the public site. Only accounts with Conversations turned on (on the Site users page) can read and write them. Delete removes a post for good; to stop a member posting, turn Conversations off on their account.'),
      ],
      'search' => $this->formBuilder()->getForm(ConversationSearchForm::class, $query),
    ];

    try {
      $listing = $this->manager->listConversationPosts($query, $this->pagerManager->findPage() + 1);
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
        ? $this->formatPlural((int) $listing['total'], 'One post.', '@count posts.')
        : $this->formatPlural((int) $listing['total'], 'One post matches.', '@count posts match.'),
    ];

    $rows = [];
    foreach ($listing['posts'] as $post) {
      $written = $this->formatDate($post['created_at']);
      if ($post['updated_at'] !== $post['created_at']) {
        $written .= ' ' . $this->t('(changed @time)', ['@time' => $this->formatDate($post['updated_at'])]);
      }
      $rows[] = [
        ['data' => ['#plain_text' => $post['title']]],
        ['data' => ['#plain_text' => $post['excerpt']]],
        ['data' => ['#plain_text' => $post['author'] . ' (' . $post['author_email'] . ')']],
        ['data' => ['#plain_text' => $written]],
        [
          'data' => [
            '#type' => 'operations',
            '#links' => [
              ['title' => $this->t('Read and delete'), 'url' => Url::fromRoute('bible_admin.conversation_delete', ['post_id' => $post['id']])],
            ],
          ],
        ],
      ];
    }

    $build['table'] = [
      '#type' => 'table',
      '#header' => [
        $this->t('Title'),
        $this->t('Beginning'),
        $this->t('Author'),
        $this->t('Written'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $query === '' ? $this->t('No member has written a post yet.') : $this->t('No post matches.'),
    ];
    $build['pager'] = ['#type' => 'pager'];
    return $build;
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }

}
