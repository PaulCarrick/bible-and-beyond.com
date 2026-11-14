<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;

/**
 * The search box above the Conversations and Prayer Wall posts: keeps the posts with every word in the title,
 * the text or the author's name or address, and those of one board when one is chosen.
 */
class ConversationSearchForm extends FormBase {

  public function getFormId(): string {
    return 'bible_admin_conversation_search';
  }

  public function buildForm(array $form, FormStateInterface $form_state, string $query = '', string $board = ''): array {
    $form['#attributes']['class'][] = 'container-inline';
    $form['board'] = [
      '#type' => 'select',
      '#title' => $this->t('Show'),
      '#options' => [
        '' => $this->t('Both'),
        'conversations' => $this->t('Conversations'),
        'prayer' => $this->t('Prayer Wall'),
      ],
      '#default_value' => $board,
    ];
    $form['query'] = [
      '#type' => 'search',
      '#title' => $this->t('Title, text, author, address or reply contains'),
      '#default_value' => $query,
      '#size' => 30,
      '#maxlength' => 200,
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['search'] = ['#type' => 'submit', '#value' => $this->t('Search')];
    if ($query !== '' || $board !== '') {
      $form['actions']['clear'] = [
        '#type' => 'link',
        '#title' => $this->t('Show all'),
        '#url' => Url::fromRoute('bible_admin.conversations'),
      ];
    }
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $parameters = array_filter([
      'query' => trim((string) $form_state->getValue('query')),
      'board' => (string) $form_state->getValue('board'),
    ], fn ($value) => $value !== '');
    $form_state->setRedirect('bible_admin.conversations', [], $parameters === [] ? [] : ['query' => $parameters]);
  }

}
