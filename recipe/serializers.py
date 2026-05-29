from rest_framework import serializers

from .models import Recipe, RecipeCategory, RecipeLike, Comment


class RecipeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeCategory
        fields = ('id', 'name')


class RecipeSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)
    username = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    category = RecipeCategorySerializer()
    total_number_of_likes = serializers.SerializerMethodField()
    total_number_of_bookmarks = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ('id', 'category', 'category_name', 'picture', 'title', 'desc',
                  'cook_time', 'ingredients', 'procedure', 'author', 'username',
                  'total_number_of_likes', 'total_number_of_bookmarks',
                  'is_liked', 'is_saved', 'comments_count')
        extra_kwargs = {
            'picture': {'required': False, 'allow_null': True}
        }

    def get_username(self, obj):
        return obj.author.username

    def get_category_name(self, obj):
        return obj.category.name

    def get_total_number_of_likes(self, obj):
        return obj.get_total_number_of_likes()

    def get_total_number_of_bookmarks(self, obj):
        return obj.get_total_number_of_bookmarks()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return RecipeLike.objects.filter(user=request.user, recipe=obj).exists()
        return False

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.bookmarked_by.filter(id=request.user.id).exists()
        return False

    def get_comments_count(self, obj):
        return obj.comments.count()

    def create(self, validated_data):
        category_data = validated_data.pop('category')
        
        # Нормализуем название категории
        category_name = category_data.get('name', 'Others').strip()
        
        # Используем get_or_create для категории
        category_instance, created = RecipeCategory.objects.get_or_create(
            name=category_name
        )
        
        recipe_instance = Recipe.objects.create(
            **validated_data,
            category=category_instance
        )
        return recipe_instance

    def update(self, instance, validated_data):
        # Обновляем категорию отдельно, чтобы не создавать новую
        if 'category' in validated_data:
            category_data = validated_data.pop('category')
            if category_data and category_data.get('name'):
                category_name = category_data.get('name').strip()
                # Получаем существующую категорию или создаем новую
                category_instance, created = RecipeCategory.objects.get_or_create(
                    name=category_name
                )
                instance.category = category_instance
        
        # Обновляем остальные поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class RecipeLikeSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = RecipeLike
        fields = ('id', 'user', 'recipe')

class CommentSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)
    author_name = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    is_author = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ('id', 'recipe', 'author', 'author_name', 'author_avatar', 
                  'text', 'created_at', 'updated_at', 'is_author')
        read_only_fields = ('id', 'author', 'created_at', 'updated_at')

    def get_author_name(self, obj):
        return obj.author.username

    def get_author_avatar(self, obj):
        if obj.author.profile.avatar:
            return obj.author.profile.avatar.url
        return None

    def get_is_author(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.author == request.user
        return False
