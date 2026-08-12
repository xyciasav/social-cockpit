CREATE TABLE `ai_activity` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`user_request` text NOT NULL,
	`provider` text,
	`model` text,
	`status` text NOT NULL,
	`created_at` integer NOT NULL,
	`error` text
);
--> statement-breakpoint
CREATE TABLE `ai_preferences` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`category` text NOT NULL,
	`preference` text NOT NULL,
	`evidence_count` integer DEFAULT 0 NOT NULL,
	`confidence` text NOT NULL,
	`editable` integer DEFAULT true NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `ai_provider_configs` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`provider_name` text NOT NULL,
	`base_url` text NOT NULL,
	`model` text NOT NULL,
	`temperature` real DEFAULT 0.4 NOT NULL,
	`max_tokens` integer DEFAULT 1200 NOT NULL,
	`system_instructions` text,
	`encrypted_secret_ref` text,
	`enabled` integer DEFAULT true NOT NULL
);
--> statement-breakpoint
CREATE TABLE `ai_tool_calls` (
	`id` text PRIMARY KEY NOT NULL,
	`activity_id` text NOT NULL,
	`workspace_id` text NOT NULL,
	`tool_name` text NOT NULL,
	`action_kind` text NOT NULL,
	`arguments` text NOT NULL,
	`result_summary` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `approvals` (
	`id` text PRIMARY KEY NOT NULL,
	`workspace_id` text NOT NULL,
	`post_id` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`requested_by` text NOT NULL,
	`requested_at` integer NOT NULL,
	`decided_at` integer,
	`decided_by` text
);
