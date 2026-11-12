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
 * Shows a member's Conversations post in full and asks before deleting it.
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
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the post "@title"?', ['@title' => $this->post['title'] ?? '']);
  }

  public function getDescription() {
    return $this->t('This permanently deletes the post for every member. It cannot be undone. The author is not told.');
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
      $this->messenger()->addStatus($this->t('Deleted the post "@title".', ['@title' => $post['title']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.conversations');
  }

}
