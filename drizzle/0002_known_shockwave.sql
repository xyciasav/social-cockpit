CREATE TABLE `events` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`campaign_id` text,
	`name` text NOT NULL,
	`description` text,
	`location` text,
	`starts_at` integer NOT NULL,
	`ends_at` integer,
	`url` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_events_workspace_start` ON `events` (`workspace_id`,`starts_at`);--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_posts` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`account_id` text NOT NULL,
	`campaign_id` text,
	`event_id` text,
	`provider_post_id` text,
	`status` text DEFAULT 'draft' NOT NULL,
	`proposed_at` integer,
	`scheduled_at` integer,
	`published_at` integer,
	`caption` text,
	`permalink` text,
	`content_type` text,
	`tone` text,
	`cta` text,
	`media_type` text,
	`historical` integer DEFAULT false NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
INSERT INTO `__new_posts`("id", "workspace_id", "account_id", "campaign_id", "event_id", "provider_post_id", "status", "proposed_at", "scheduled_at", "published_at", "caption", "permalink", "content_type", "tone", "cta", "media_type", "historical", "created_at", "updated_at") SELECT "id", "workspace_id", "account_id", "campaign_id", "event_id", "provider_post_id", "status", "proposed_at", "scheduled_at", "published_at", "caption", "permalink", "content_type", "tone", "cta", "media_type", "historical", "created_at", "updated_at" FROM `posts`;--> statement-breakpoint
DROP TABLE `posts`;--> statement-breakpoint
ALTER TABLE `__new_posts` RENAME TO `posts`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE UNIQUE INDEX `uq_posts_account_provider` ON `posts` (`account_id`,`provider_post_id`);--> statement-breakpoint
CREATE INDEX `idx_posts_workspace_status_time` ON `posts` (`workspace_id`,`status`,`proposed_at`);--> statement-breakpoint
ALTER TABLE `approvals` ADD `note` text;--> statement-breakpoint
CREATE UNIQUE INDEX `uq_approvals_post` ON `approvals` (`post_id`);--> statement-breakpoint
CREATE INDEX `idx_approvals_workspace_status` ON `approvals` (`workspace_id`,`status`);