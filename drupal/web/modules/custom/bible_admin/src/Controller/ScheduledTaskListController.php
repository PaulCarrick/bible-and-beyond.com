<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * The scheduled tasks of the tasks this user may see: the coming ones by date, and the past ones (latest first)
 * folded away below, each with Edit and Remove.
 */
class ScheduledTaskListController extends ControllerBase {

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
        '#value' => $this->t('Who does which task on which date. To schedule one, use Schedule beside the task on the <a href=":tasks">Tasks</a> page and choose the site user and one of its next four dates.', [
          ':tasks' => Url::fromRoute('bible_admin.tasks')->toString(),
        ]),
      ],
    ];
    try {
      $schedules = $this->manager->listScheduledTasks();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $showOwner = $this->currentUser()->hasPermission('administer signatures and tasks');
    $coming = array_values(array_filter($schedules, fn ($schedule) => !$schedule['past']));
    $past = array_reverse(array_values(array_filter($schedules, fn ($schedule) => $schedule['past'])));

    $build['coming'] = $this->table($coming, $showOwner, $this->t('Nothing is scheduled from today on.'));
    if ($past) {
      $build['past'] = [
        '#type' => 'details',
        '#title' => $this->t('Past (@count)', ['@count' => count($past)]),
        '#open' => FALSE,
        'table' => $this->table($past, $showOwner, ''),
      ];
    }
    return $build;
  }

  private function table(array $schedules, bool $showOwner, $empty): array {
    $rows = [];
    foreach ($schedules as $schedule) {
      $links = [
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.scheduled_task_edit', ['schedule_id' => $schedule['id']])],
        ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.scheduled_task_remove', ['schedule_id' => $schedule['id']])],
      ];
      $row = [
        ['data' => ['#plain_text' => $this->formatDay($schedule['on_date'])]],
        ['data' => ['#plain_text' => $schedule['task_name']]],
        ['data' => ['#plain_text' => $schedule['user_label']]],
      ];
      if ($showOwner) {
        $row[] = ['data' => ['#plain_text' => $schedule['owner_name']]];
      }
      $row[] = ['data' => ['#plain_text' => $schedule['created_by_name']]];
      $row[] = ['data' => ['#type' => 'operations', '#links' => $links]];
      $rows[] = $row;
    }
    $header = [$this->t('Date'), $this->t('Task'), $this->t('Site user')];
    if ($showOwner) {
      $header[] = $this->t('Task owner');
    }
    $header[] = $this->t('Scheduled by');
    $header[] = $this->t('Operations');
    return ['#type' => 'table', '#header' => $header, '#rows' => $rows, '#empty' => $empty];
  }

  /**
   * A day such as "Sun, Nov 22, 2026" (a date with no time, so no time zone change).
   */
  private function formatDay(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $date->format('D, M j, Y');
  }

}
