CREATE TABLE `resources` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`type` text NOT NULL,
	`title` text NOT NULL,
	`content` text,
	`url` text,
	`object_key` text,
	`filename` text,
	`mime_type` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_resources_workspace_type` ON `resources` (`workspace_id`,`type`);--> statement-breakpoint
CREATE TABLE `workspace_settings` (
	`workspace_id` text PRIMARY KEY NOT NULL,
	`tone_prompt` text DEFAULT '' NOT NULL,
	`organization_info` text DEFAULT '' NOT NULL,
	`llm_base_url` text DEFAULT 'http://host.docker.internal:1234' NOT NULL,
	`llm_model` text DEFAULT 'qwen' NOT NULL,
	`temperature` real DEFAULT 0.4 NOT NULL,
	`max_tokens` integer DEFAULT 2000 NOT NULL,
	`updated_at` integer NOT NULL
);
