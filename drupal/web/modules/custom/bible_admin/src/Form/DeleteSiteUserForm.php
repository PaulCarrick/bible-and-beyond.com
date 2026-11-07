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
 * Asks before deleting an account of the main site, which also deletes its notes and email subscriptions.
 */
class DeleteSiteUserForm extends ConfirmFormBase {

  private ?array $user = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_site_user';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?int $user_id = NULL): array {
    try {
      $this->user = $this->manager->getSiteUser((int) $user_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the site users'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('user_id', (int) $this->user['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Delete the account @email?', ['@email' => $this->user['email'] ?? '']);
  }

  public function getDescription() {
    return $this->t('This permanently deletes the account with its @notes and @emails. It cannot be undone; the visitor could only set up a new, empty account.', [
      '@notes' => $this->formatPlural((int) ($this->user['note_count'] ?? 0), 'one note', '@count notes'),
      '@emails' => $this->formatPlural((int) ($this->user['subscription_count'] ?? 0), 'one daily devotional email', '@count daily devotional emails'),
    ]);
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.site_users');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $user = $this->manager->deleteSiteUser((int) $form_state->get('user_id'));
      $this->messenger()->addStatus($this->t('Deleted the account @email.', ['@email' => $user['email']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.site_users');
  }

}
