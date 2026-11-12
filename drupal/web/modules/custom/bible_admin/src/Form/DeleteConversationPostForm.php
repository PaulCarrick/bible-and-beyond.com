<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Link;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Shows a member's Conversations post in full with its replies (each with a link to delete it alone), and asks
 * before deleting the post with its replies.
 */
class DeleteConversationPostForm extends ConfirmFormBase {

  private ?array $post = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_conversation_post';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $post_id = NULL): array {
    try {
      $this->post = $this->manager->getConversationPost((int) $post_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to Conversations'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('post_id', (int) $this->post['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    $form['post'] = [
      '#type' => 'details',
      '#title' => $this->t('The post, by @author (@email)', ['@author' => $this->post['author'], '@email' => $this->post['author_email']]),
      '#open' => TRUE,
      '#weight' => -10,
      // The text was cleaned with the site's allowlist when it was saved; #markup filters it again here.
      'body' => ['#markup' => $this->post['body']],
    ];
    $form['replies'] = [
      '#type' => 'details',
      '#title' => $this->formatPlural(count($this->post['replies']), 'One reply', '@count replies'),
      '#open' => TRUE,
      '#weight' => -9,
    ];
    foreach ($this->post['replies'] as $reply) {
      $form['replies']['reply_' . $reply['id']] = [
        '#type' => 'container',
        'byline' => [
          '#type' => 'html_tag',
          '#tag' => 'p',
          '#value' => $this->t('<strong>@author</strong> (@email), @time', [
            '@author' => $reply['author'],
            '@email' => $reply['author_email'],
            '@time' => date('j M Y H:i', strtotime($reply['created_at']) ?: 0),
          ]),
        ],
        // Cleaned when saved; #markup filters it again here.
        'body' => ['#markup' => $reply['body']],
        'delete' => Link::fromTextAndUrl($this->t('Delete this reply'), Url::fromRoute('bible_admin.conversation_reply_delete', ['reply_id' => $reply['id']]))->toRenderable(),
        'rule' => ['#markup' => '<hr>'],
      ];
    }
    if ($this->post['replies'] === []) {
      $form['replies']['none'] = ['#markup' => $this->t('No one has replied.')];
    }
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the post "@title"?', ['@title' => $this->post['title'] ?? '']);
  }

  public function getDescription() {
    return $this->t('Delete removes the post and its @replies for every member. It cannot be undone. The authors are not told.', [
      '@replies' => $this->formatPlural(count($this->post['replies'] ?? []), 'one reply', '@count replies'),
    ]);
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.conversations');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $post = $this->manager->deleteConversationPost((int) $form_state->get('post_id'));
      $this->messenger()->addStatus($this->t('Deleted the post "@title" and its replies.', ['@title' => $post['title']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.conversations');
  }

}
