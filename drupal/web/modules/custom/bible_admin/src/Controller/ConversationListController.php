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
 * The members' posts of Conversations and the Prayer Wall on the public site, newest first, with a search and pages, so an
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
    $request = $this->requestStack->getCurrentRequest();
    $query = trim((string) $request->query->get('query', ''));
    $board = (string) $request->query->get('board', '');
    if (!in_array($board, ['conversations', 'prayer'], TRUE)) {
      $board = '';
    }
    $boardNames = ['conversations' => $this->t('Conversations'), 'prayer' => $this->t('Prayer Wall')];
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('These are the posts that members write on the Conversations and Prayer Wall pages of the public site, with their replies (each post shows only on its own page; the Where column says which). Anyone can read them; only accounts with Conversations turned on (on the Site users page) can write on either. "Read and delete" shows a post with its replies, where you can delete the post (with its replies) or any one reply; it is gone for good. To stop a member posting, turn Conversations off on their account.'),
      ],
      'search' => $this->formBuilder()->getForm(ConversationSearchForm::class, $query, $board),
    ];

    try {
      $listing = $this->manager->listConversationPosts($query, $this->pagerManager->findPage() + 1, $board);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $this->pagerManager->createPager((int) $listing['total'], (int) $listing['per_page']);

    $build['count'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $query === '' && $board === ''
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
        ['data' => ['#plain_text' => (string) ($boardNames[$post['board'] ?? 'conversations'] ?? '') . self::prayerOptions($post)]],
        ['data' => ['#plain_text' => $post['excerpt']]],
        ['data' => ['#plain_text' => $post['author'] . ' (' . $post['author_email'] . ')']],
        ['data' => ['#plain_text' => $written]],
        ['data' => ['#plain_text' => number_format((int) ($post['reply_count'] ?? 0))]],
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
        $this->t('Where'),
        $this->t('Beginning'),
        $this->t('Author'),
        $this->t('Written'),
        $this->t('Replies'),
        $this->t('Operations'),
      ],
      '#rows' => $rows,
      '#empty' => $query === '' && $board === '' ? $this->t('No member has written a post yet.') : $this->t('No post matches.'),
    ];
    $build['pager'] = ['#type' => 'pager'];
    return $build;
  }

  private function formatDate(string $iso): string {
    $time = strtotime($iso);
    return $time === FALSE ? '' : $this->dateFormatter->format($time, 'short');
  }


  /**
   * The Prayer Wall choices of a post, such as " (private, anonymous)", or nothing.
   *
   * The administrators see the real author of an anonymous post and every private one.
   */
  public static function prayerOptions(array $post): string {
    $options = array_filter([
      // A post to one member (2026-11-23): only the two of them (and administrators) see it.
      !empty($post['recipient']) ? (string) t('private, to @name (@address) only', ['@name' => $post['recipient'], '@address' => $post['recipient_email'] ?? '']) : '',
      !empty($post['is_private']) ? (string) t('private') : '',
      !empty($post['is_anonymous']) ? (string) t('anonymous') : '',
      !empty($post['email_to_prayer_list']) ? (string) t('emailed to the prayer list') : '',
      !empty($post['answered_at']) ? (string) t('answered') : '',
    ]);
    return $options ? ' (' . implode(', ', $options) . ')' : '';
  }

}
