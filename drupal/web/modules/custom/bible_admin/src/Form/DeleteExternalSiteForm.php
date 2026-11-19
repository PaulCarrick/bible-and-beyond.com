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
 * Asks before taking a site off the External sites list (the site itself is not touched).
 */
class DeleteExternalSiteForm extends ConfirmFormBase {

  private ?array $site = NULL;

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_delete_external_site';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $site_id = NULL): array {
    try {
      $this->site = $this->manager->getExternalSite((int) $site_id);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the external sites'), '#url' => $this->getCancelUrl()]];
    }
    $form_state->set('site_id', (int) $this->site['id']);
    $form = parent::buildForm($form, $form_state);
    $form['#cache'] = ['max-age' => 0];
    return $form;
  }

  public function getQuestion() {
    return $this->t('Take “@name” off the list?', ['@name' => $this->site['name'] ?? '']);
  }

  public function getDescription() {
    return $this->t('Only the link and its notes are deleted here; nothing changes on the site itself or in your account there.');
  }

  public function getConfirmText() {
    return $this->t('Delete');
  }

  public function getCancelUrl(): Url {
    return Url::fromRoute('bible_admin.external_sites');
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    try {
      $site = $this->manager->deleteExternalSite((int) $form_state->get('site_id'));
      $this->messenger()->addStatus($this->t('Deleted “@name” from the list.', ['@name' => $site['name']]));
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    $form_state->setRedirect('bible_admin.external_sites');
  }

}
