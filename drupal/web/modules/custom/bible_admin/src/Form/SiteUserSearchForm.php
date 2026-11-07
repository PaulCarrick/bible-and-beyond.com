<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;

/**
 * The search box above the list of site users: keeps the accounts whose address contains the words.
 */
class SiteUserSearchForm extends FormBase {

  public function getFormId(): string {
    return 'bible_admin_site_user_search';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $query = ''): array {
    $form['#attributes']['class'][] = 'container-inline';
    $form['query'] = [
      '#type' => 'search',
      '#title' => $this->t('Email address contains'),
      '#default_value' => $query,
      '#size' => 30,
      '#maxlength' => 200,
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['search'] = ['#type' => 'submit', '#value' => $this->t('Search')];
    if ($query !== '') {
      $form['actions']['clear'] = [
        '#type' => 'link',
        '#title' => $this->t('Show all'),
        '#url' => Url::fromRoute('bible_admin.site_users'),
      ];
    }
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $query = trim((string) $form_state->getValue('query'));
    $form_state->setRedirect('bible_admin.site_users', [], $query === '' ? [] : ['query' => ['query' => $query]]);
  }

}
