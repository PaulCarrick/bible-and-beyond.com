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
 * Shows one reply to a Conversations post and asks before deleting it. Afterwards it returns to the post.
 */
class DeleteConversationReplyForm extends ConfirmFormBase {

  private ?array $reply = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_conversation_reply';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $reply_id = NULL): array {
    try {
      $this->reply = $this->manager->getConversationReply((int) $reply_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to Conversations'), '#url' => Url::fromRoute('bible_admin.conversations')]];
    }
    $form_state->set('reply_id', (int) $this->reply['id']);
    $form_state->set('post_id', (int) $this->reply['post_id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    $form['reply'] = [
      '#type' => 'details',
      '#title' => $this->t('The reply, by @author (@email)', ['@author' => $this->reply['author'], '@email' => $this->reply['author_email']]),
      '#open' => TRUE,
      '#weight' => -10,
      // Cleaned with the site's allowlist when it was saved; #markup filters it again here.
      'body' => ['#markup' => $this->reply['body']],
    ];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete this reply to "@title"?', ['@title' => $this->reply['post_title'] ?? '']);
  }

  public function getDescription() {
    return $this->t('This permanently deletes the reply for every member. The post and its other replies stay. It cannot be undone, and the author is not told.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return $this->reply
      ? Url::fromRoute('bible_admin.conversation_delete', ['post_id' => $this->reply['post_id']])
      : Url::fromRoute('bible_admin.conversations');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $this->manager->deleteConversationReply((int) $form_state->get('reply_id'));
      $this->messenger()->addStatus($this->t('Deleted the reply.'));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.conversation_delete', ['post_id' => $form_state->get('post_id')]);
  }

}
