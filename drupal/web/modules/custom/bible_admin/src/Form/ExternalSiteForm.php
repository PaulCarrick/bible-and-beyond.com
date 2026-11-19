<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds an external site or changes one: a name, its address (http or https; the ML service checks it) and notes.
 */
class ExternalSiteForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_external_site';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $site_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $site = NULL;
    if ($site_id !== NULL) {
      try {
        $site = $this->manager->getExternalSite((int) $site_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the external sites'), '#url' => Url::fromRoute('bible_admin.external_sites')]];
      }
      $form_state->set('site_id', (int) $site['id']);
    }
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Name'),
      '#default_value' => $site['name'] ?? '',
      '#maxlength' => 200,
      '#required' => TRUE,
      '#description' => $this->t('Such as “Kindle reader”.'),
    ];
    $form['address'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Address'),
      '#default_value' => $site['address'] ?? '',
      '#maxlength' => 2000,
      '#required' => TRUE,
      '#placeholder' => 'https://read.amazon.com',
      '#description' => $this->t('The web address to open: the site’s home, or a page in it (copy it from the browser’s address bar). For the Kindle web reader, https://read.amazon.com. Do not put a user name or password in it: sign in on the site itself.'),
    ];
    $form['sign_in_address'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Sign-in address (optional)'),
      '#default_value' => $site['sign_in_address'] ?? '',
      '#maxlength' => 2000,
      '#description' => $this->t('The site’s sign-in page. When it is filled in, the list has a Sign in button beside Open, for when the site has signed you out (this page cannot see whether you are signed in to another site). Leave it empty for a site that shows its own Sign in, such as the Kindle web reader.'),
    ];
    $form['show_on_site'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Show it in the site’s sidebar'),
      '#default_value' => $site['show_on_site'] ?? TRUE,
      '#description' => $this->t('Visitors to the site then see its name, as a link, under “External sites” in the sidebar (the group appears only when a site is shown). Your notes and the sign-in address are never shown to them. Clear it for a site that is only for you.'),
    ];
    $form['notes'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Notes'),
      '#default_value' => $site['notes'] ?? '',
      '#rows' => 3,
      '#description' => $this->t('Anything to remember about the site, shown in this list only (never to visitors). Not a password.'),
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $site === NULL ? $this->t('Add the site') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.external_sites'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $siteId = $form_state->get('site_id');
    try {
      $site = $this->manager->saveExternalSite(
        $siteId === NULL ? NULL : (int) $siteId,
        (string) $form_state->getValue('name'),
        (string) $form_state->getValue('address'),
        (string) $form_state->getValue('notes'),
        trim((string) $form_state->getValue('sign_in_address')),
        (bool) $form_state->getValue('show_on_site'),
      );
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($siteId === NULL
      ? $this->t('Added “@name”. Use Open to open it in its own window.', ['@name' => $site['name']])
      : $this->t('Saved “@name”.', ['@name' => $site['name']]));
    $form_state->setRedirect('bible_admin.external_sites');
  }

}
