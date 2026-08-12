CREATE TABLE `social_accounts` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`platform` text NOT NULL,
	`name` text NOT NULL,
	`followers` integer
);
--> statement-breakpoint
CREATE TABLE `campaigns` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`name` text NOT NULL,
	`starts_at` integer,
	`ends_at` integer
);
--> statement-breakpoint
CREATE TABLE `analytics_imports` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`provider` text NOT NULL,
	`filename` text NOT NULL,
	`object_key` text NOT NULL,
	`status` text NOT NULL,
	`mapping` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `performance_insights` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`account_id` text,
	`platform` text,
	`finding` text NOT NULL,
	`evidence` text NOT NULL,
	`sample_size` integer NOT NULL,
	`confidence` text NOT NULL,
	`generated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `posts` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`account_id` text NOT NULL,
	`campaign_id` text,
	`provider_post_id` text,
	`published_at` integer NOT NULL,
	`caption` text,
	`permalink` text,
	`content_type` text,
	`tone` text,
	`cta` text,
	`media_type` text,
	`historical` integer DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_posts_account_provider` ON `posts` (`account_id`,`provider_post_id`);--> statement-breakpoint
CREATE TABLE `analytics_snapshots` (
	`id` text PRIMARY KEY NOT NULL,
	`post_id` text NOT NULL,
	`provider` text NOT NULL,
	`captured_at` integer NOT NULL,
	`impressions` integer,
	`reach` integer,
	`engagement` integer,
	`engagement_rate` real,
	`raw_metrics` text,
	`source_record_hash` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_snapshot_source_hash` ON `analytics_snapshots` (`source_record_hash`);--> statement-breakpoint
CREATE TABLE `workspaces` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`created_at` integer NOT NULL
);
