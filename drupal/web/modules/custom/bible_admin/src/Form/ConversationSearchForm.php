<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;

/**
 * The search box above the Conversations posts: keeps the posts with every word in the title, the text or
 * the author's name or address.
 */
class ConversationSearchForm extends FormBase {

  public function getFormId(): string {
    return 'bible_admin_conversation_search';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $query = ''): array {
    $form['#attributes']['class'][] = 'container-inline';
    $form['query'] = [
      '#type' => 'search',
      '#title' => $this->t('Title, text, author, address or reply contains'),
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
        '#url' => Url::fromRoute('bible_admin.conversations'),
      ];
    }
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $query = trim((string) $form_state->getValue('query'));
    $form_state->setRedirect('bible_admin.conversations', [], $query === '' ? [] : ['query' => ['query' => $query]]);
  }

}
