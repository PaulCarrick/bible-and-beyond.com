<?php

declare(strict_types=1);

namespace Drupal\bible_admin;

use Drupal\Component\Utility\Html;
use Drupal\filter\Entity\FilterFormat;

/**
 * The editor (CKEditor 5, text format group_email) for the group pages' formatted boxes: the message of Send a
 * message, a scheduled message, a group's notes and Email a member (the owner's request, 2026-11-17: "wherever the
 * user can enter formatted text"). The ML service cleans what it writes (contact.check_rich_text). Where the format
 * or the editor is missing, a plain box, whose words are sent as text.
 */
final class GroupEditor {

  public const FORMAT = 'group_email';

  /**
   * The form element: the editor, or a plain box when the user may not use the format.
   *
   * @param string $default
   *   What is there already: HTML from the editor, or plain text from before (shown as paragraphs).
   */
  public static function field(string $title, string $default, int $rows, bool $required, string $description = ''): array {
    $format = FilterFormat::load(self::FORMAT);
    if ($format && $format->access('use')) {
      return [
        '#type' => 'text_format',
        '#title' => $title,
        '#format' => self::FORMAT,
        '#allowed_formats' => [self::FORMAT],
        '#default_value' => self::isHtml($default) ? $default : self::paragraphs($default),
        '#rows' => $rows,
        '#required' => $required,
        '#description' => $description,
        '#after_build' => [[self::class, 'hideFormatHelp']],
      ];
    }
    return [
      '#type' => 'textarea',
      '#title' => $title,
      '#default_value' => self::isHtml($default) ? trim(Html::decodeEntities(strip_tags(str_replace(['</p>', '<br>'], ["\n\n", "\n"], $default)))) : $default,
      '#rows' => $rows,
      '#required' => $required,
      '#description' => $description,
    ];
  }

  /**
   * What the element gave: ['html' => ...] from the editor, ['text' => ...] from the plain box.
   */
  public static function value(mixed $value): array {
    return is_array($value) ? ['html' => (string) ($value['value'] ?? '')] : ['text' => (string) $value];
  }

  /**
   * Whether stored words came from the editor (cleaned HTML always starts with a tag).
   */
  public static function isHtml(string $stored): bool {
    return str_starts_with(ltrim($stored), '<');
  }

  /**
   * Plain text from before the editor, as paragraphs for it.
   */
  public static function paragraphs(string $text): string {
    $text = trim(str_replace("\r\n", "\n", $text));
    if ($text === '') {
      return '';
    }
    $paragraphs = preg_split("/\n{2,}/", $text);
    return implode('', array_map(fn ($paragraph) => '<p>' . nl2br(Html::escape($paragraph), FALSE) . '</p>', $paragraphs));
  }

  /**
   * Takes away the "About text formats" link and the format's guidelines: there is only the one format.
   */
  public static function hideFormatHelp(array $element): array {
    unset($element['format']['help'], $element['format']['guidelines']);
    return $element;
  }

}
