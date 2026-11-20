<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\RedirectResponse;

/**
 * The FAQ questions page (2026-11-20): the site's FAQ list under its headings, each question with Up, Down, Edit and
 * Delete, and the words about the site that are sent to the AI with every question.
 */
class FaqQuestionListController extends ControllerBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function build(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('The questions visitors can choose on the FAQ page, in this order under their headings. The AI writes each answer the first time someone opens it and keeps it for a month. A reworded question gets a new answer, and its note (FAQ notes) moves with it. Changes show on the site at once.'),
      ],
      'add' => [
        '#type' => 'link',
        '#title' => $this->t('Add a question'),
        '#url' => Url::fromRoute('bible_admin.faq_question_add'),
        '#attributes' => ['class' => ['button', 'button--primary', 'button--small']],
        '#prefix' => '<p>',
        '#suffix' => '</p>',
      ],
    ];
    try {
      $list = $this->manager->getFaqQuestionList();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }

    if ($list['source'] === 'built-in') {
      $build['source'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('This site uses the questions built into Bible and Beyond. Your first change makes this list the site’s own, to change as you like.'),
      ];
    }

    $build['about'] = [
      '#type' => 'details',
      '#title' => $this->t('About this site (sent to the AI with every question)'),
      '#open' => TRUE,
      'text' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $list['about'] !== '' ? $this->t('@about', ['@about' => $list['about']]) : $this->t('None: the AI answers as for any Bible study site.'),
      ],
      'edit' => [
        '#type' => 'link',
        '#title' => $this->t('Change these words'),
        '#url' => Url::fromRoute('bible_admin.faq_about'),
        '#attributes' => ['class' => ['button', 'button--small']],
      ],
    ];

    foreach ($list['groups'] as $index => $group) {
      $rows = [];
      $count = count($group['questions']);
      foreach ($group['questions'] as $position => $entry) {
        $links = [];
        if ($position > 0) {
          $links['up'] = ['title' => $this->t('Up'), 'url' => Url::fromRoute('bible_admin.faq_question_move', ['question_id' => $entry['id'], 'direction' => 'up'])];
        }
        if ($position < $count - 1) {
          $links['down'] = ['title' => $this->t('Down'), 'url' => Url::fromRoute('bible_admin.faq_question_move', ['question_id' => $entry['id'], 'direction' => 'down'])];
        }
        $links['edit'] = ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.faq_question_edit', ['question_id' => $entry['id']])];
        $links['delete'] = ['title' => $this->t('Delete'), 'url' => Url::fromRoute('bible_admin.faq_question_delete', ['question_id' => $entry['id']])];
        $rows[] = [
          ['data' => ['#plain_text' => $entry['question']]],
          ['data' => ['#type' => 'operations', '#links' => $links]],
        ];
      }
      $build['group_' . $index] = [
        '#type' => 'table',
        '#caption' => $group['heading'],
        '#header' => [$this->t('Question'), $this->t('Operations')],
        '#rows' => $rows,
      ];
    }

    if ($list['source'] === 'site') {
      $build['built_in'] = [
        '#type' => 'link',
        '#title' => $this->t('Go back to the built-in questions'),
        '#url' => Url::fromRoute('bible_admin.faq_built_in'),
        '#attributes' => ['class' => ['button', 'button--small', 'button--danger']],
        '#prefix' => '<p>',
        '#suffix' => '</p>',
      ];
    }
    return $build;
  }

  /**
   * Up or Down: one place within its heading, then back to the list.
   */
  public function move(string $question_id, string $direction): RedirectResponse {
    try {
      $this->manager->moveFaqQuestion((int) $question_id, $direction);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
    }
    return $this->redirect('bible_admin.faq_questions');
  }

}
